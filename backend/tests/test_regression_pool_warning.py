"""CRITICAL REGRESSION: the 95% connection-pool warning at line 120 must never be lost.

Scenario: 1,000 lines; line 120 is `WARN Connection pool usage reached 95%`; later, 143 database timeout errors.
The system must (1) detect and aggregate the 143 repeated errors and (2) preserve the earlier warning in
the critical signals, the evidence pack sent to the model, the final incident analysis and the five-line summary,
even when the model omits it or the AI call fails.
"""

import pytest

from app.ai.analyzer import analyze
from app.ai.prompts.v1 import build_user_prompt
from app.ai.providers.mock_provider import MockProvider
from app.ai.summary import render_summary
from app.pipeline.orchestrator import run_pipeline
from app.samples.generator import POOL_TIMEOUT_COUNT, POOL_WARNING_LINE, POOL_WARNING_MESSAGE, generate_sample
from tests.conftest import make_settings, provider_error


@pytest.fixture(scope="module", params=["text", "jsonl"])
def scenario(request):
    text = generate_sample("pool_exhaustion", 1000, request.param)
    return text, run_pipeline(text, make_settings())


def _warning_items(pack):
    return [i for i in pack.items if i.first_line == POOL_WARNING_LINE]


def test_dataset_shape(scenario):
    text, _ = scenario
    lines = text.splitlines()
    assert len(lines) == 1000
    assert "WARN" in lines[POOL_WARNING_LINE - 1] and POOL_WARNING_MESSAGE in lines[POOL_WARNING_LINE - 1]
    assert sum("Database query timed out" in ln for ln in lines) == POOL_TIMEOUT_COUNT == 143
    first_timeout = next(i for i, ln in enumerate(lines, 1) if "Database query timed out" in ln)
    assert first_timeout > POOL_WARNING_LINE


def test_repeated_errors_are_detected_and_aggregated(scenario):
    _, result = scenario
    timeouts = [g for g in result.groups if "Database query timed out" in g.example_message]
    assert len(timeouts) == 1 and timeouts[0].count == 143
    assert "db_timeout" in timeouts[0].patterns
    assert result.stats["pattern_counts"]["db_timeout"] == 143


def test_warning_is_a_must_include_critical_signal(scenario):
    _, result = scenario
    sig = next((s for s in result.signals if s.line_no == POOL_WARNING_LINE), None)
    assert sig is not None, "95% pool warning missing from critical signals"
    assert sig.must_include and sig.severity == "WARN"
    assert {"precursor", "threshold", "rare_high_severity"} <= set(sig.tags)
    assert "Precedes 143× ERROR" in sig.reason


def test_warning_is_in_evidence_pack_and_prompt(scenario):
    _, result = scenario
    items = _warning_items(result.evidence)
    assert items and items[0].must_include, "95% pool warning missing from evidence pack"
    assert items[0].first_ts is not None
    prompt = build_user_prompt(result.evidence)
    assert POOL_WARNING_MESSAGE in prompt and '"first_line": 120' in prompt


@pytest.mark.parametrize("token_budget", [6000, 800, 50])
def test_warning_survives_any_token_budget(token_budget):
    result = run_pipeline(generate_sample("pool_exhaustion"), make_settings(evidence_token_budget=token_budget, evidence_max_items=2))
    assert _warning_items(result.evidence), f"warning dropped at budget={token_budget}"


async def test_warning_in_final_analysis_and_summary_with_mock_ai(scenario):
    _, result = scenario
    analysis = await analyze(result.evidence, MockProvider(), make_settings())
    warn_id = _warning_items(result.evidence)[0].id
    assert warn_id in analysis.critical_evidence_ids
    summary = render_summary(analysis, result.evidence, result.stats)
    assert "L120" in summary[2] and POOL_WARNING_MESSAGE in summary[2]
    assert "143×" in summary[2]


async def test_warning_preserved_even_if_model_ignores_it(scenario, scripted):
    _, result = scenario
    burst = next(i for i in result.evidence.items if i.count == 143)
    model_output = {
        "incident_title": "Database timeouts",
        "impact": "Queries failed.",
        "observed_facts": [{"statement": "143 timeouts", "evidence_ids": [burst.id]}],
        "hypotheses": [{"statement": "Database slow", "confidence": "low", "rationale": "", "evidence_ids": [burst.id]}],
        "recommendations": [{"action": "Check the database.", "priority": "immediate", "evidence_ids": []}],
        "critical_evidence_ids": [],
        "overall_confidence": "low",
        "uncertainty_notes": [],
    }
    analysis = await analyze(result.evidence, scripted([model_output]), make_settings())
    warn_id = _warning_items(result.evidence)[0].id
    assert warn_id in analysis.critical_evidence_ids and warn_id in analysis.reattached_evidence_ids
    assert any("L120" in f.statement for f in analysis.observed_facts)
    assert "L120" in render_summary(analysis, result.evidence, result.stats)[2]


async def test_warning_preserved_when_ai_fails(scenario, scripted):
    _, result = scenario
    analysis = await analyze(result.evidence, scripted([provider_error("timeout", True)]), make_settings())
    assert analysis.ai_status == "fallback"
    warn_id = _warning_items(result.evidence)[0].id
    assert warn_id in analysis.critical_evidence_ids
    assert "L120" in render_summary(analysis, result.evidence, result.stats)[2]


def test_end_to_end_through_api(client):
    resp = client.post("/api/v1/samples/analyze", json={"scenario": "pool_exhaustion", "lines": 1000})
    detail = client.get(f"/api/v1/analyses/{resp.json()['id']}").json()
    assert detail["signals"][0]["line_no"] == 120 and detail["signals"][0]["must_include"]
    assert any(i["first_line"] == 120 and i["must_include"] for i in detail["evidence"]["items"])
    assert "L120" in detail["summary_lines"][2]
    assert any(g["count"] == 143 for g in detail["groups"])
