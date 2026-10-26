"""AI analysis: prompt -> provider (timeout, bounded retries) -> JSON -> Pydantic -> reference checks -> guarantees.

Whatever happens, analyze() returns a valid IncidentAnalysis. On any failure it falls back to the deterministic
heuristic analysis and records why (ai_status="fallback").
"""

import asyncio
import json
import logging
import re

from pydantic import ValidationError

from app.ai.heuristics import build_heuristic_analysis
from app.ai.prompts.v1 import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from app.ai.providers.base import AIProvider, ProviderError
from app.ai.schemas import AI_OUTPUT_JSON_SCHEMA, AIAnalysis, IncidentAnalysis, ObservedFact
from app.core.config import Settings
from app.pipeline.evidence import EvidencePack, estimate_tokens

log = logging.getLogger("loglens.ai")

STATS_REF = "STATS"  # allowed pseudo-reference to the deterministic file statistics
_CERTAINTY = re.compile(
    r"(?<!not )(?<!never )\b(confirmed|proven|definitively|definitely|certainly|undoubtedly)\b", re.I
)
_CONF_ORDER = {"low": 0, "medium": 1, "high": 2}


class OutputRejected(Exception):
    """The model output failed parsing or validation; message is safe to echo back to the model."""


def extract_json(text: str) -> dict:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.S)
    if fence:
        cleaned = fence.group(1).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise OutputRejected("response did not contain a JSON object")
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise OutputRejected(f"invalid JSON ({exc.msg} at char {exc.pos})") from exc
    if not isinstance(data, dict):
        raise OutputRejected("top-level JSON value must be an object")
    return data


def validate_output(text: str, pack: EvidencePack) -> tuple[AIAnalysis, list[str]]:
    """Parse and validate model output against the schema and the evidence pack. Returns (analysis, warnings)."""
    data = extract_json(text)
    try:
        analysis = AIAnalysis.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        raise OutputRejected(f"schema validation failed at {'/'.join(map(str, first['loc']))}: {first['msg']}") from exc

    valid_ids = set(pack.by_id()) | {STATS_REF}
    warnings: list[str] = []

    def keep(ids: list[str], where: str) -> list[str]:
        unknown = [i for i in ids if i not in valid_ids]
        if unknown:
            warnings.append(f"Removed unknown evidence id(s) {unknown} from {where}")
        return [i for i in dict.fromkeys(ids) if i in valid_ids]

    for fact in analysis.observed_facts:
        fact.evidence_ids = keep(fact.evidence_ids, "observed_facts")
    analysis.observed_facts = [f for f in analysis.observed_facts if f.evidence_ids]
    if not analysis.observed_facts:
        raise OutputRejected("no observed fact cites a valid evidence id")

    for hyp in analysis.hypotheses:
        hyp.evidence_ids = keep(hyp.evidence_ids, "hypotheses")
        if _CERTAINTY.search(hyp.statement) or _CERTAINTY.search(hyp.rationale):
            raise OutputRejected("hypotheses must not claim certainty (e.g. 'confirmed'); logs cannot confirm a cause")
        distinct = {i for i in hyp.evidence_ids if i != STATS_REF}
        if hyp.confidence == "high" and len(distinct) < 2:
            hyp.confidence = "medium"
            warnings.append("Capped a 'high' confidence hypothesis supported by fewer than two evidence items")
    analysis.hypotheses = [h for h in analysis.hypotheses if h.evidence_ids]

    for rec in analysis.recommendations:
        rec.evidence_ids = keep(rec.evidence_ids, "recommendations")
    analysis.critical_evidence_ids = keep(analysis.critical_evidence_ids, "critical_evidence_ids")

    top = max((_CONF_ORDER[h.confidence] for h in analysis.hypotheses), default=0)
    if _CONF_ORDER[analysis.overall_confidence] > top:
        analysis.overall_confidence = ["low", "medium", "high"][top]  # type: ignore[assignment]
        warnings.append("Lowered overall confidence to match the strongest hypothesis")
    return analysis, warnings


def fit_pack_to_budget(pack: EvidencePack, budget_tokens: int) -> EvidencePack:
    """Drop lowest-priority non-must-include items until the rendered prompt fits the budget."""
    fitted = pack.model_copy(deep=True)
    while estimate_tokens(SYSTEM_PROMPT + build_user_prompt(fitted)) > budget_tokens:
        removable = [i for i in fitted.items if not i.must_include]
        if not removable:
            break
        victim = min(removable, key=lambda i: (i.risk_score, -i.first_line))
        fitted.items.remove(victim)
        fitted.omitted_group_count += 1
    return fitted


def enforce_must_include(analysis: AIAnalysis, pack: EvidencePack) -> list[str]:
    """Deterministic guarantee: every must_include signal ends up in the analysis, whatever the model returned."""
    by_id = pack.by_id()
    reattached = []
    cited = {i for fact in analysis.observed_facts for i in fact.evidence_ids}
    for eid in pack.must_include_ids():
        if eid not in analysis.critical_evidence_ids:
            analysis.critical_evidence_ids.append(eid)
            reattached.append(eid)
        if eid not in cited and len(analysis.observed_facts) < 10:
            item = by_id[eid]
            analysis.observed_facts.append(
                ObservedFact(
                    statement=f"Critical signal preserved by LogLens: {item.severity} at {item.line_label()}"
                    + (f" ({item.first_ts})" if item.first_ts else "")
                    + f' "{item.text[:120]}". Reason: {item.reason or "deterministic rule"}.',
                    evidence_ids=[eid],
                )
            )
            if eid not in reattached:
                reattached.append(eid)
    return reattached


async def analyze(pack: EvidencePack, provider: AIProvider | None, settings: Settings) -> IncidentAnalysis:
    if provider is None:
        return _finalize(
            build_heuristic_analysis(pack, "fallback"),
            pack,
            "disabled",
            "AI disabled by configuration",
            "none",
            "none",
            0,
            [],
            {},
        )

    prompt_budget = settings.evidence_token_budget + estimate_tokens(SYSTEM_PROMPT) + 600
    fitted = fit_pack_to_budget(pack, prompt_budget)
    correction: str | None = None
    failure: str | None = None
    attempts = 0
    max_attempts = 1 + max(0, settings.ai_max_retries)

    while attempts < max_attempts:
        attempts += 1
        user_prompt = build_user_prompt(fitted, correction)
        try:
            response = await asyncio.wait_for(
                provider.complete(
                    system=SYSTEM_PROMPT,
                    user=user_prompt,
                    json_schema=AI_OUTPUT_JSON_SCHEMA,
                    max_tokens=settings.ai_max_output_tokens,
                    timeout=settings.ai_timeout_seconds,
                ),
                timeout=settings.ai_timeout_seconds + min(2.0, settings.ai_timeout_seconds),
            )
        except TimeoutError:
            failure = "timeout"
            log.warning("ai_timeout", extra={"attempt": attempts, "provider": provider.name})
            await _backoff(settings, attempts, max_attempts)
            continue
        except ProviderError as exc:
            failure = exc.kind
            log.warning("ai_provider_error", extra={"attempt": attempts, "kind": exc.kind, "error": str(exc)})
            if not exc.retryable:
                break
            await _backoff(settings, attempts, max_attempts)
            continue
        except Exception:  # noqa: BLE001 - a provider bug must never fail the analysis
            failure = "provider_error"
            log.exception("ai_unexpected_error")
            break

        try:
            analysis, warnings = validate_output(response.text, fitted)
        except OutputRejected as exc:
            failure = "invalid_output"
            correction = str(exc)
            log.warning("ai_output_rejected", extra={"attempt": attempts, "reason": correction})
            continue
        return _finalize(
            analysis, fitted, "ok", None, provider.name, response.model, attempts, warnings, response.usage
        )

    reason = {
        "timeout": "AI request timed out",
        "rate_limited": "AI provider rate limit reached",
        "provider_error": "AI provider error",
        "refusal": "AI provider declined the request",
        "not_configured": "AI provider not configured (missing or invalid API key)",
        "bad_request": "AI provider rejected the request",
        "invalid_output": f"AI output failed validation ({correction})",
    }.get(failure or "", "AI analysis failed")
    return _finalize(
        build_heuristic_analysis(fitted, "fallback"),
        fitted,
        "fallback",
        reason,
        provider.name,
        provider.model,
        attempts,
        [],
        {},
    )


async def _backoff(settings: Settings, attempt: int, max_attempts: int) -> None:
    if attempt < max_attempts and settings.ai_backoff_seconds > 0:
        await asyncio.sleep(min(settings.ai_backoff_seconds * 2 ** (attempt - 1), 8))


def _finalize(
    analysis: AIAnalysis,
    pack: EvidencePack,
    status: str,
    reason: str | None,
    provider: str,
    model: str,
    attempts: int,
    warnings: list[str],
    usage: dict[str, int],
) -> IncidentAnalysis:
    if status != "ok":
        analysis.overall_confidence = "low"
        for hyp in analysis.hypotheses:
            hyp.confidence = "low"
    reattached = enforce_must_include(analysis, pack)
    return IncidentAnalysis(
        **analysis.model_dump(),
        ai_status=status,  # type: ignore[arg-type]
        failure_reason=reason,
        provider=provider,
        model=model,
        prompt_version=PROMPT_VERSION,
        attempts=attempts,
        reattached_evidence_ids=reattached,
        validation_warnings=warnings,
        usage=usage,
    )
