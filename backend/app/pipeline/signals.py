"""Deterministic critical-signal extraction and risk scoring.

The LLM is never trusted to find critical events on its own. These rules decide what MUST reach
the final analysis (must_include=True), independently of volume.
"""

import math
from dataclasses import dataclass

from app.core.config import Settings
from app.pipeline.models import (
    SEVERITY_RANK,
    SIGNAL_PRIORITY,
    EventGroup,
    Severity,
    Signal,
    SignalKind,
    is_high_severity,
)
from app.pipeline.patterns import PATTERNS_BY_ID, PRECURSOR_LINKS, looks_like_injection

SEVERITY_WEIGHT = {
    Severity.CRITICAL: 50,
    Severity.ERROR: 30,
    Severity.WARN: 15,
    Severity.UNKNOWN: 5,
    Severity.INFO: 2,
    Severity.DEBUG: 0,
}
RARITY_BONUS = 10
PRECURSOR_BONUS = 25
THRESHOLD_BONUS = 15
INJECTION_BONUS = 10
MAX_RARE_MUST_INCLUDE = 8


@dataclass
class _Burst:
    group: EventGroup
    patterns: set[str]


def _volume_points(count: int) -> int:
    return min(20, round(8 * math.log10(count))) if count > 1 else 0


def _find_bursts(groups: list[EventGroup], settings: Settings) -> list[_Burst]:
    return [
        _Burst(g, set(g.patterns))
        for g in groups
        if SEVERITY_RANK.get(g.severity, 0) >= SEVERITY_RANK[Severity.ERROR] and g.count >= settings.burst_min_count
    ]


def detect_signals(groups: list[EventGroup], settings: Settings) -> list[Signal]:
    """Score groups (in place) and return signals sorted by priority and risk."""
    by_fp = {g.fingerprint: g for g in groups}
    bursts = _find_bursts(groups, settings)
    signals: dict[str, Signal] = {}

    def add(group: EventGroup, kind: SignalKind, reason: str, must: bool, line_no: int | None = None) -> None:
        existing = signals.get(group.fingerprint)
        if existing is None:
            existing = Signal(
                kind=kind,
                severity=group.severity,
                line_no=line_no or group.first_line,
                line_numbers=group.sample_lines(),
                ts=group.first_ts,
                service=group.service,
                message=group.example_message,
                pattern_ids=list(group.patterns),
                group_fingerprint=group.fingerprint,
                count=group.count,
            )
            signals[group.fingerprint] = existing
        if kind not in existing.tags:
            existing.tags.append(kind)
        if reason not in existing.reasons:
            existing.reasons.append(reason)
        existing.must_include = existing.must_include or must
        existing.kind = min(existing.tags, key=SIGNAL_PRIORITY.index)

    for group in groups:
        breakdown = {"severity": SEVERITY_WEIGHT.get(group.severity, 0)}
        if group.patterns:
            breakdown["pattern"] = max(PATTERNS_BY_ID[p].weight for p in group.patterns)
        if group.count > 1:
            breakdown["volume"] = _volume_points(group.count)
        high = is_high_severity(group.severity)
        pattern_titles = ", ".join(PATTERNS_BY_ID[p].title.lower() for p in group.patterns)

        if group.severity == Severity.CRITICAL:
            add(group, SignalKind.CRITICAL, f"CRITICAL severity ({group.count}×)", True)

        if high and group.count <= settings.rare_max_count:
            breakdown["rarity"] = RARITY_BONUS
            add(
                group,
                SignalKind.RARE_HIGH_SEVERITY,
                f"Rare {group.severity} (occurs {group.count}× in file)",
                must=bool(group.patterns) or group.severity != Severity.WARN,
            )

        if group.patterns and (high or group.severity == Severity.UNKNOWN):
            add(group, SignalKind.PATTERN, f"Matches pattern: {pattern_titles}", must=False)

        value = group.peak_percent
        if value is not None and value >= settings.threshold_percent and group.severity != Severity.DEBUG:
            breakdown["threshold"] = THRESHOLD_BONUS
            add(
                group,
                SignalKind.THRESHOLD,
                f"Resource threshold breach (peak {value:g}% ≥ {settings.threshold_percent}% at L{group.peak_line})",
                True,
            )

        if group.severity in (Severity.WARN, Severity.ERROR, Severity.UNKNOWN) and group.patterns:
            for burst in bursts:
                if burst.group.fingerprint == group.fingerprint or burst.group.first_line <= group.first_line:
                    continue
                linked = set().union(*(PRECURSOR_LINKS.get(p, set()) for p in group.patterns))
                if linked & burst.patterns and burst.group.count > group.count:
                    breakdown["precursor"] = PRECURSOR_BONUS
                    burst_titles = ", ".join(PATTERNS_BY_ID[p].title.lower() for p in sorted(burst.patterns))
                    add(
                        group,
                        SignalKind.PRECURSOR,
                        f"Precedes {burst.group.count}× {burst.group.severity} {burst_titles} "
                        f"starting at L{burst.group.first_line}",
                        True,
                    )
                    break

        if looks_like_injection(group.example_message):
            breakdown["injection"] = INJECTION_BONUS
            add(group, SignalKind.PROMPT_INJECTION, "Contains text resembling instructions to an AI (untrusted)", True)

        group.score_breakdown = breakdown
        group.risk_score = sum(breakdown.values())

    for sig in signals.values():
        sig.risk_score = by_fp[sig.group_fingerprint].risk_score if sig.group_fingerprint else 0

    ordered = sorted(signals.values(), key=lambda s: (not s.must_include, -s.risk_score, s.line_no))
    # Bound rare-only must_include signals so a noisy file cannot crowd out everything else.
    rare_only_seen = 0
    for sig in ordered:
        if sig.must_include and sig.tags == [SignalKind.RARE_HIGH_SEVERITY]:
            rare_only_seen += 1
            if rare_only_seen > MAX_RARE_MUST_INCLUDE:
                sig.must_include = False
    return sorted(ordered, key=lambda s: (not s.must_include, -s.risk_score, s.line_no))
