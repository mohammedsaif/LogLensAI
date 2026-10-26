from app.pipeline.evidence import INJECTION_PLACEHOLDER, estimate_tokens
from app.pipeline.orchestrator import run_pipeline
from app.samples.generator import generate_sample
from tests.conftest import make_settings


def test_evidence_ids_are_stable_and_must_include_first():
    result = run_pipeline(generate_sample("pool_exhaustion"), make_settings())
    items = result.evidence.items
    assert [i.id for i in items] == [f"E{n}" for n in range(1, len(items) + 1)]
    flags = [i.must_include for i in items]
    assert flags == sorted(flags, reverse=True)  # all must_include items precede the rest
    assert items[0].first_line == 120


def test_must_include_survives_tiny_token_budget():
    settings = make_settings(evidence_token_budget=50, evidence_max_items=1)
    result = run_pipeline(generate_sample("pool_exhaustion"), settings)
    must = [i for i in result.evidence.items if i.must_include]
    assert any(i.first_line == 120 for i in must)
    assert all(not i.must_include for i in result.evidence.items if i not in must)
    assert result.evidence.omitted_group_count > 0
    assert all(len(i.text) <= 100 for i in must)  # shortened, not dropped


def test_token_budget_is_respected_for_optional_items():
    settings = make_settings(evidence_token_budget=1500)
    result = run_pipeline(generate_sample("memory_leak", 3000), settings)
    assert result.evidence.token_estimate <= 1500 or all(i.must_include for i in result.evidence.items)


def test_prompt_injection_text_is_withheld_from_evidence():
    result = run_pipeline(generate_sample("prompt_injection"), make_settings())
    flagged = [i for i in result.evidence.items if i.kind == "prompt_injection"]
    assert len(flagged) == 2
    assert all(i.text == INJECTION_PLACEHOLDER for i in flagged)
    assert {i.first_line for i in flagged} == {83, 115}


def test_estimate_tokens_is_monotonic():
    assert estimate_tokens("a" * 400) > estimate_tokens("a" * 40)
    assert estimate_tokens({"k": "v"}) >= 1
