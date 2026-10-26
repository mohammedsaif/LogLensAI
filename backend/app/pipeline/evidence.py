"""Evidence selection: a bounded, redacted, referenced evidence pack for the AI step.

Order of inclusion:
1. Every must_include signal (never dropped; text is shortened if the budget is tight).
2. Other signals by risk score.
3. Remaining WARN+/pattern groups by risk score, until the token or item budget is reached.
"""

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.pipeline.models import EventGroup, Signal, SignalKind, is_high_severity
from app.pipeline.redaction import Redactor

INJECTION_PLACEHOLDER = "[suspected prompt-injection text withheld by LogLens; inspect the raw line]"


class EvidenceItem(BaseModel):
    id: str
    source: str  # signal | group
    kind: str | None = None
    severity: str
    service: str | None = None
    count: int
    first_line: int
    last_line: int
    line_refs: list[int]
    first_ts: str | None = None
    last_ts: str | None = None
    text: str
    template: str
    pattern_ids: list[str] = Field(default_factory=list)
    must_include: bool = False
    reason: str | None = None
    risk_score: int = 0
    group_fingerprint: str | None = None

    def line_label(self) -> str:
        return f"L{self.first_line}" if self.first_line == self.last_line else f"L{self.first_line}–L{self.last_line}"


class EvidencePack(BaseModel):
    items: list[EvidenceItem]
    stats: dict[str, Any]
    omitted_group_count: int = 0
    token_estimate: int = 0
    redaction_counts: dict[str, int] = Field(default_factory=dict)

    def by_id(self) -> dict[str, EvidenceItem]:
        return {item.id: item for item in self.items}

    def must_include_ids(self) -> list[str]:
        return [item.id for item in self.items if item.must_include]


def estimate_tokens(payload: Any) -> int:
    """Cheap, conservative token estimate (~4 chars/token) used for budgeting before the API call."""
    text = payload if isinstance(payload, str) else json.dumps(payload, default=str)
    return max(1, len(text) // 4 + 1)


def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z") if dt else None


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def compact_stats(stats: dict[str, Any]) -> dict[str, Any]:
    return {
        "total_lines": stats["total_lines"],
        "event_count": stats["event_count"],
        "severity_counts": stats["severity_counts"],
        "affected_services": stats["affected_services"],
        "services": [s["name"] for s in stats["services"][:15]],
        "time_range": stats["time_range"],
        "pattern_counts": stats["pattern_counts"],
        "malformed_lines": stats["malformed_lines"],
        "duplicate_event_count": stats["duplicate_event_count"],
    }


def build_evidence_pack(
    groups: list[EventGroup],
    signals: list[Signal],
    stats: dict[str, Any],
    *,
    token_budget: int,
    max_items: int,
    redact_ips: bool = True,
) -> EvidencePack:
    redactor = Redactor(redact_ips)
    groups_by_fp = {g.fingerprint: g for g in groups}
    candidates: list[tuple[EventGroup, Signal | None]] = []
    seen: set[str] = set()
    for sig in signals:
        if sig.group_fingerprint and sig.group_fingerprint not in seen:
            candidates.append((groups_by_fp[sig.group_fingerprint], sig))
            seen.add(sig.group_fingerprint)
    for group in sorted(groups, key=lambda g: (-g.risk_score, g.first_line)):
        if group.fingerprint in seen:
            continue
        if is_high_severity(group.severity) or group.patterns:
            candidates.append((group, None))
            seen.add(group.fingerprint)

    stats_compact = compact_stats(stats)
    used_tokens = estimate_tokens(stats_compact) + 400  # stats + JSON envelope overhead
    items: list[EvidenceItem] = []
    omitted = 0

    def make_item(group: EventGroup, sig: Signal | None, text_limit: int) -> EvidenceItem:
        is_injection = sig is not None and SignalKind.PROMPT_INJECTION in sig.tags
        text = INJECTION_PLACEHOLDER if is_injection else _truncate(redactor.redact(group.example_message), text_limit)
        template = INJECTION_PLACEHOLDER if is_injection else _truncate(redactor.redact(group.template), text_limit)
        return EvidenceItem(
            id=f"E{len(items) + 1}",
            source="signal" if sig else "group",
            kind=sig.kind.value if sig else None,
            severity=group.severity,
            service=group.service,
            count=group.count,
            first_line=group.first_line,
            last_line=group.last_line,
            line_refs=group.sample_lines(head=3, tail=2),
            first_ts=_iso(group.first_ts),
            last_ts=_iso(group.last_ts),
            text=text,
            template=template,
            pattern_ids=list(group.patterns),
            must_include=bool(sig and sig.must_include),
            reason=sig.reason if sig else None,
            risk_score=group.risk_score,
            group_fingerprint=group.fingerprint,
        )

    for group, sig in candidates:
        must = bool(sig and sig.must_include)
        if not must and len(items) >= max_items:
            omitted += 1
            continue
        item = make_item(group, sig, 300)
        cost = estimate_tokens(item.model_dump(exclude_none=True))
        if used_tokens + cost > token_budget:
            if not must:
                omitted += 1
                continue
            item = make_item(group, sig, 100)  # must_include items are shortened, never dropped
            cost = estimate_tokens(item.model_dump(exclude_none=True))
        items.append(item)
        used_tokens += cost

    return EvidencePack(
        items=items,
        stats=stats_compact,
        omitted_group_count=omitted,
        token_estimate=used_tokens,
        redaction_counts=dict(redactor.counts),
    )
