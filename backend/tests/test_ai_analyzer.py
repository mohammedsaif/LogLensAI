"""AI response validation, retries, timeouts, fallback and deterministic guarantees (all mocked)."""

import asyncio
import json

import pytest

from app.ai.analyzer import analyze, extract_json, fit_pack_to_budget, validate_output
from app.ai.prompts.v1 import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from app.ai.providers.mock_provider import MockProvider
from app.ai.schemas import AI_OUTPUT_JSON_SCHEMA, AIAnalysis
from app.pipeline.evidence import estimate_tokens
from app.pipeline.orchestrator import run_pipeline
from app.samples.generator import generate_sample
from tests.conftest import make_settings, provider_error


@pytest.fixture(scope="module")
def pack():
    return run_pipeline(generate_sample("pool_exhaustion"), make_settings()).evidence


def good_output(pack, **overrides) -> dict:
    must = pack.must_include_ids()
    burst = next(i for i in pack.items if i.count == 143)
    data = {
        "incident_title": "Database timeouts in order-service after pool pressure",
        "impact": "Order reads failed repeatedly for about 15 minutes.",
        "observed_facts": [
            {"statement": "143 database timeouts in order-service", "evidence_ids": [burst.id]},
            {"statement": "Pool usage reached 95% at L120 before the burst", "evidence_ids": [must[0]]},
        ],
        "hypotheses": [
            {
                "statement": "The connection pool saturated, so queries waited and timed out.",
                "confidence": "high",
                "rationale": "Pool warning precedes the timeouts.",
                "evidence_ids": [must[0], burst.id],
            }
        ],
        "recommendations": [{"action": "Inspect pool metrics.", "priority": "immediate", "evidence_ids": [must[0]]}],
        "critical_evidence_ids": must,
        "overall_confidence": "high",
        "uncertainty_notes": [],
    }
    data.update(overrides)
    return data


async def test_valid_response_is_accepted(pack, scripted):
    provider = scripted([good_output(pack)])
    result = await analyze(pack, provider, make_settings())
    assert result.ai_status == "ok" and result.attempts == 1
    assert result.prompt_version == PROMPT_VERSION
    assert result.overall_confidence == "high"
    call = provider.calls[0]
    assert call["system"] == SYSTEM_PROMPT and call["json_schema"] == AI_OUTPUT_JSON_SCHEMA


async def test_json_in_code_fence_is_accepted(pack, scripted):
    provider = scripted(["Here you go:\n```json\n" + json.dumps(good_output(pack)) + "\n```"])
    assert (await analyze(pack, provider, make_settings())).ai_status == "ok"


async def test_invalid_json_is_retried_with_correction_then_succeeds(pack, scripted):
    provider = scripted(["{not json", good_output(pack)])
    result = await analyze(pack, provider, make_settings())
    assert result.ai_status == "ok" and result.attempts == 2
    assert "rejected by the validator" in provider.calls[1]["user"]


async def test_schema_violation_exhausts_retries_then_falls_back(pack, scripted):
    bad = good_output(pack)
    del bad["impact"]
    provider = scripted([bad])
    result = await analyze(pack, provider, make_settings(ai_max_retries=2))
    assert result.ai_status == "fallback" and result.attempts == 3
    assert "failed validation" in result.failure_reason
    assert result.overall_confidence == "low"


async def test_extra_fields_are_rejected(pack):
    with pytest.raises(Exception, match="schema validation failed"):
        validate_output(json.dumps(good_output(pack, run_command="rm -rf /")), pack)


async def test_timeout_falls_back(pack, scripted):
    async def hang(**_):
        await asyncio.sleep(10)

    provider = scripted([hang])
    result = await analyze(pack, provider, make_settings(ai_timeout_seconds=0.05, ai_max_retries=1))
    assert result.ai_status == "fallback"
    assert result.failure_reason == "AI request timed out"
    assert result.attempts == 2


async def test_retryable_provider_error_then_success(pack, scripted):
    provider = scripted([provider_error("rate_limited", True), good_output(pack)])
    result = await analyze(pack, provider, make_settings())
    assert result.ai_status == "ok" and result.attempts == 2


async def test_non_retryable_error_falls_back_immediately(pack, scripted):
    provider = scripted([provider_error("not_configured", False)])
    result = await analyze(pack, provider, make_settings(ai_max_retries=5))
    assert result.ai_status == "fallback" and result.attempts == 1
    assert "not configured" in result.failure_reason


async def test_refusal_falls_back(pack, scripted):
    result = await analyze(pack, scripted([provider_error("refusal", False)]), make_settings())
    assert result.failure_reason == "AI provider declined the request"


async def test_unexpected_provider_exception_falls_back(pack, scripted):
    result = await analyze(pack, scripted([RuntimeError("bug")]), make_settings())
    assert result.ai_status == "fallback"


async def test_unknown_evidence_ids_are_removed_with_warning(pack, scripted):
    out = good_output(pack)
    out["observed_facts"][0]["evidence_ids"].append("E999")
    result = await analyze(pack, scripted([out]), make_settings())
    assert result.ai_status == "ok"
    assert all("E999" not in f.evidence_ids for f in result.observed_facts)
    assert any("E999" in w for w in result.validation_warnings)


async def test_facts_without_valid_references_are_rejected(pack):
    out = good_output(pack, observed_facts=[{"statement": "made up", "evidence_ids": ["E404"]}])
    with pytest.raises(Exception, match="no observed fact"):
        validate_output(json.dumps(out), pack)


@pytest.mark.parametrize("word", ["confirmed", "definitely", "proven"])
async def test_certainty_claims_in_hypotheses_are_rejected(pack, word):
    out = good_output(pack)
    out["hypotheses"][0]["statement"] = f"The root cause is {word} to be the pool."
    with pytest.raises(Exception, match="must not claim certainty"):
        validate_output(json.dumps(out), pack)


async def test_negated_certainty_is_allowed(pack):
    out = good_output(pack)
    out["hypotheses"][0]["statement"] = "Pool saturation is likely but not confirmed."
    analysis, _ = validate_output(json.dumps(out), pack)
    assert analysis.hypotheses


async def test_high_confidence_with_single_evidence_is_capped(pack):
    out = good_output(pack)
    out["hypotheses"][0]["evidence_ids"] = [pack.must_include_ids()[0]]
    analysis, warnings = validate_output(json.dumps(out), pack)
    assert analysis.hypotheses[0].confidence == "medium"
    assert analysis.overall_confidence == "medium"
    assert warnings


async def test_omitted_must_include_signal_is_reattached(pack, scripted):
    out = good_output(pack, critical_evidence_ids=[])
    burst = next(i for i in pack.items if i.count == 143)
    out["observed_facts"] = [{"statement": "143 timeouts", "evidence_ids": [burst.id]}]
    out["hypotheses"] = []
    out["overall_confidence"] = "low"
    result = await analyze(pack, scripted([out]), make_settings())
    must = pack.must_include_ids()
    assert set(must) <= set(result.critical_evidence_ids)
    assert set(must) <= set(result.reattached_evidence_ids)
    assert any("L120" in f.statement and "preserved by LogLens" in f.statement for f in result.observed_facts)


async def test_disabled_provider_returns_deterministic_analysis(pack):
    result = await analyze(pack, None, make_settings())
    assert result.ai_status == "disabled" and result.provider == "none"
    assert pack.must_include_ids()[0] in result.critical_evidence_ids


async def test_mock_provider_runs_full_validation_path(pack):
    result = await analyze(pack, MockProvider(), make_settings())
    assert result.ai_status == "ok" and result.provider == "mock"
    assert result.overall_confidence in ("low", "medium")
    assert any("Mock" in n or "mock" in n for n in result.uncertainty_notes)


def test_fit_pack_to_budget_keeps_must_include():
    big = run_pipeline(generate_sample("prompt_injection", 5000), make_settings(evidence_token_budget=20000)).evidence
    fitted = fit_pack_to_budget(big, 1200)
    assert set(big.must_include_ids()) <= {i.id for i in fitted.items}
    assert len(fitted.items) < len(big.items)
    assert estimate_tokens(SYSTEM_PROMPT + build_user_prompt(fitted)) <= 1200 or all(i.must_include for i in fitted.items)


def test_extract_json_errors():
    with pytest.raises(Exception, match="did not contain"):
        extract_json("no braces here")
    with pytest.raises(Exception, match="invalid JSON"):
        extract_json("{'single': quotes}")


def test_pydantic_schema_matches_provider_schema_fields():
    assert set(AI_OUTPUT_JSON_SCHEMA["required"]) == set(AIAnalysis.model_fields)
