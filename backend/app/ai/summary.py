"""Renders the user-facing five-line summary from validated structured data (never from free model text)."""

import re
from typing import Any

from app.ai.schemas import IncidentAnalysis
from app.pipeline.evidence import EvidenceItem, EvidencePack

SUMMARY_LABELS = ("Incident", "Impact", "Evidence", "Possible Cause", "Recommended Action")
MAX_LINE = 600


def _one_line(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _ref(item: EvidenceItem) -> str:
    when = f" @ {item.first_ts}" if item.first_ts else ""
    body = item.text if item.count == 1 else item.template
    count = "" if item.count == 1 else f"{item.count}× "
    return f'{item.line_label()}{when} {count}{item.severity} "{_clip(_one_line(body), 70)}"'


def _id_refs(ids: list[str], by_id: dict[str, EvidenceItem]) -> str:
    labels = [f"{i}→{by_id[i].line_label()}" for i in ids if i in by_id]
    return f" [{', '.join(labels)}]" if labels else ""


def render_summary(analysis: IncidentAnalysis, pack: EvidencePack, stats: dict[str, Any]) -> list[str]:
    by_id = pack.by_id()

    time_range = stats.get("time_range") or {}
    window = f" ({time_range['start']} to {time_range['end']})" if time_range.get("start") else ""
    incident = f"Incident: {_one_line(analysis.incident_title)}{window}"

    n_services = len(stats.get("affected_services") or [])
    impact = (
        f"Impact: {_one_line(analysis.impact)} Observed: {stats.get('errors', 0)} errors, "
        f"{stats.get('warnings', 0)} warnings, {stats.get('critical', 0)} critical events; "
        f"{n_services} service(s) with errors."
    )

    # Evidence: critical (must_include) signals first, so a rare precursor can never be crowded out by volume.
    critical = [by_id[i] for i in analysis.critical_evidence_ids if i in by_id]
    # Withheld prompt-injection items are reported in uncertainty notes, not in the Evidence line.
    critical.sort(key=lambda i: (i.kind == "prompt_injection", not i.must_include, -i.risk_score, i.first_line))
    critical = [c for c in critical if c.kind != "prompt_injection"] or critical
    rest = [i for i in pack.items if i.id not in {c.id for c in critical}]
    others = sorted((i for i in rest if i.severity in ("ERROR", "CRITICAL")), key=lambda i: -i.count) or sorted(
        (i for i in rest if i.severity == "WARN"), key=lambda i: -i.count
    )
    shown = critical[:3] + others[: max(1, 4 - len(critical[:3]))]
    refs = "; ".join(f"{_ref(i)}{' (critical signal)' if i.must_include else ''}" for i in shown)
    extra = len(critical) - 3
    evidence = f"Evidence: {refs}" + (f"; +{extra} more critical signal(s)" if extra > 0 else "")
    if not shown:
        evidence = "Evidence: No WARN/ERROR/CRITICAL evidence items; see file statistics."

    if analysis.hypotheses:
        top = max(analysis.hypotheses, key=lambda h: {"low": 0, "medium": 1, "high": 2}[h.confidence])
        cause = (
            f"Possible Cause (hypothesis, {top.confidence} confidence, not confirmed): "
            f"{_one_line(top.statement)}{_id_refs(top.evidence_ids, by_id)}"
        )
    else:
        cause = "Possible Cause (hypothesis, low confidence, not confirmed): Not enough evidence to propose a cause."

    order = {"immediate": 0, "short_term": 1, "long_term": 2}
    recs = sorted(analysis.recommendations, key=lambda r: order[r.priority])
    action = f"Recommended Action: {_one_line(recs[0].action)}"
    if len(recs) > 1:
        action += f" Then: {_one_line(recs[1].action)}"

    lines = [incident, impact, evidence, cause, action]
    return [_clip(line, MAX_LINE) for line in lines]
