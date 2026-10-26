"""Rule-based analysis built only from the evidence pack.

Used by (a) the deterministic fallback when the AI call fails and (b) the offline MockProvider.
Every statement is derived from evidence items, so nothing here is invented.
"""

from dataclasses import dataclass

from app.ai.schemas import AIAnalysis, Confidence, Hypothesis, ObservedFact, Recommendation
from app.pipeline.evidence import EvidenceItem, EvidencePack
from app.pipeline.patterns import PATTERNS_BY_ID, PRECURSOR_LINKS


@dataclass(frozen=True)
class Knowledge:
    title: str
    hypothesis: str
    actions: tuple[tuple[str, str], ...]  # (action, priority)


KB: dict[str, Knowledge] = {
    "pool_exhaustion": Knowledge(
        "Database connection pool exhaustion",
        "The database connection pool is saturated: connections are held too long (slow queries, leaked connections "
        "or long transactions) or the pool is undersized for current load.",
        (
            (
                "Check connection-pool metrics (active, idle, waiting) and the database's active sessions; look for "
                "long-running queries or transactions holding connections.",
                "immediate",
            ),
            (
                "If saturation is verified, temporarily raise the pool size or shed load, and review recent deploys "
                "that changed query patterns or pool settings.",
                "short_term",
            ),
        ),
    ),
    "db_timeout": Knowledge(
        "Database query timeouts",
        "The database is responding slowly (lock contention, slow queries or resource saturation), so queries exceed "
        "their timeout.",
        (
            ("Inspect database latency, locks and slow-query logs for the affected time window.", "immediate"),
            (
                "Review query plans and indexes for the timed-out queries; add circuit breaking so retries do not "
                "amplify load.",
                "short_term",
            ),
        ),
    ),
    "auth_failure": Knowledge(
        "Authentication failures",
        "Repeated authentication failures suggest a credential-stuffing or brute-force attempt, or a client using "
        "expired or rotated credentials.",
        (
            ("Identify the source addresses and accounts involved; rate-limit or block abusive sources.", "immediate"),
            (
                "Verify lockout policy and check internal clients for recently rotated or expired credentials.",
                "short_term",
            ),
        ),
    ),
    "memory_pressure": Knowledge(
        "Memory exhaustion",
        "Memory usage grows until the process is killed, consistent with a memory leak or an undersized memory limit.",
        (
            (
                "Capture a heap profile from an affected instance before it restarts and compare memory growth over time.",
                "immediate",
            ),
            (
                "Temporarily raise the memory limit or schedule rolling restarts while the leak is investigated.",
                "short_term",
            ),
        ),
    ),
    "service_failure": Knowledge(
        "Service unavailability",
        "A downstream dependency became unavailable or unhealthy, causing upstream requests to fail.",
        (
            (
                "Check health, restarts and recent deploys of the failing upstream service and its dependencies.",
                "immediate",
            ),
            ("Verify circuit breakers, retries and timeouts so failures do not cascade.", "short_term"),
        ),
    ),
    "disk_pressure": Knowledge(
        "Disk or filesystem pressure",
        "A volume is running out of space or became read-only, causing writes to fail.",
        (
            ("Check disk usage and inode usage on the affected hosts; free space or expand the volume.", "immediate"),
            ("Add log rotation / retention limits and disk-usage alerts.", "long_term"),
        ),
    ),
    "rate_limit": Knowledge(
        "Rate limiting / throttling",
        "Request volume exceeded a rate limit, so callers were throttled.",
        (
            ("Identify the callers being throttled and whether traffic increased unexpectedly.", "immediate"),
            ("Add client-side backoff and review quota settings.", "short_term"),
        ),
    ),
}


def _short(text: str, limit: int = 90) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _describe(item: EvidenceItem) -> str:
    where = f" in {item.service}" if item.service else ""
    when = f" at {item.first_ts}" if item.first_ts and item.count == 1 else ""
    if item.count == 1:
        return f'{item.severity}{where} at {item.line_label()}{when}: "{_short(item.text)}"'
    span = f", {item.first_ts} to {item.last_ts}" if item.first_ts and item.last_ts else ""
    return f'{item.count}× {item.severity}{where}: "{_short(item.template)}" ({item.line_label()}{span})'


def _main_pattern(item: EvidenceItem) -> str | None:
    for pid in item.pattern_ids:
        if pid in KB:
            return pid
    return None


def _find_precursor_pairs(items: list[EvidenceItem]) -> list[tuple[EvidenceItem, EvidenceItem]]:
    bursts = [i for i in items if i.severity in ("ERROR", "CRITICAL") and i.count > 1]
    pairs = []
    for item in items:
        if item.kind != "precursor":
            continue
        linked = set().union(*(PRECURSOR_LINKS.get(p, set()) for p in item.pattern_ids))
        for burst in sorted(bursts, key=lambda b: -b.count):
            if burst.first_line > item.first_line and linked & set(burst.pattern_ids):
                pairs.append((item, burst))
                break
    return pairs


def build_heuristic_analysis(pack: EvidencePack, mode: str = "fallback") -> AIAnalysis:
    items = pack.items
    stats = pack.stats
    affected = stats.get("affected_services", [])
    must_ids = pack.must_include_ids()

    errors = [i for i in items if i.severity in ("ERROR", "CRITICAL")]
    dominant = max(errors, key=lambda i: (i.count, i.risk_score), default=None) or (
        max(items, key=lambda i: i.risk_score, default=None)
    )
    pairs = _find_precursor_pairs(items)

    if dominant is None:
        return AIAnalysis(
            incident_title="No incident detected",
            impact="No warnings, errors or critical events were found in the uploaded log.",
            observed_facts=[
                ObservedFact(statement="The file contains no WARN, ERROR or CRITICAL events.", evidence_ids=["STATS"])
            ],
            hypotheses=[],
            recommendations=[
                Recommendation(action="No action needed based on these logs.", priority="long_term", evidence_ids=[])
            ],
            critical_evidence_ids=[],
            overall_confidence="low",
            uncertainty_notes=["No evidence items were selected; the summary is based on file statistics only."],
        )

    dom_pattern = _main_pattern(dominant)
    if pairs:
        pre, burst = pairs[0]
        pre_kb = KB.get(_main_pattern(pre) or "")
        burst_kb = KB.get(_main_pattern(burst) or "")
        title = f"{burst_kb.title if burst_kb else 'Error burst'} after {pre_kb.title.lower() if pre_kb else 'an early warning'}"
    elif dom_pattern:
        title = KB[dom_pattern].title
    elif dominant.severity in ("ERROR", "CRITICAL"):
        title = f"{dominant.severity} events in {dominant.service or 'unknown service'}"
    else:
        title = "Warnings detected; no error burst"
    if dominant.service and dominant.service not in title:
        title += f" ({dominant.service})"

    impact = (
        f"{dominant.count} {dominant.severity} event(s) from {dominant.service or 'an unknown service'} "
        f'("{_short(dominant.template, 70)}")'
    )
    if affected:
        impact += f"; services with errors: {', '.join(affected[:6])}"
    impact += "."

    ordered = [i for i in items if i.must_include] + sorted(
        (i for i in items if not i.must_include), key=lambda i: (-i.risk_score, i.first_line)
    )
    facts = [ObservedFact(statement=_describe(i), evidence_ids=[i.id]) for i in ordered[:6]]

    hypotheses: list[Hypothesis] = []
    for pre, burst in pairs[:2]:
        pre_kb = KB.get(_main_pattern(pre) or "")
        confidence: Confidence = "medium" if mode == "mock" else "low"
        statement = (
            (
                f"The {pre.severity} at {pre.line_label()} ({_short(pre.text, 60)})"
                if pre.count == 1
                else f"{pre.count}× {pre.severity} at {pre.line_label()} ({_short(pre.template, 60)})"
            )
            + f" preceded {burst.count}× "
            f"{burst.severity} events starting at L{burst.first_line}; "
            + (
                pre_kb.hypothesis[0].lower() + pre_kb.hypothesis[1:]
                if pre_kb
                else "the early condition is a likely contributing cause."
            )
        )
        hypotheses.append(
            Hypothesis(
                statement=statement,
                confidence=confidence,
                rationale="Temporal order: a resource-pressure warning in a related category appears before the error burst.",
                evidence_ids=[pre.id, burst.id],
            )
        )
    if dom_pattern and not any(dominant.id in h.evidence_ids for h in hypotheses):
        hypotheses.append(
            Hypothesis(
                statement=KB[dom_pattern].hypothesis,
                confidence="low",
                rationale=f"Pattern match on the largest error group ({PATTERNS_BY_ID[dom_pattern].title.lower()}).",
                evidence_ids=[dominant.id],
            )
        )

    recs: list[Recommendation] = []
    seen_actions: set[str] = set()
    sources = [p for pair in pairs for p in pair] + [dominant]
    for item in sources:
        kb = KB.get(_main_pattern(item) or "")
        if not kb:
            continue
        for action, priority in kb.actions:
            if action not in seen_actions and len(recs) < 4:
                seen_actions.add(action)
                recs.append(Recommendation(action=action, priority=priority, evidence_ids=[item.id]))  # type: ignore[arg-type]
    if not recs:
        recs.append(
            Recommendation(
                action=f"Inspect the raw lines around {dominant.line_label()} and correlate with deploys or infrastructure changes.",
                priority="immediate",
                evidence_ids=[dominant.id],
            )
        )

    notes: list[str] = []
    if mode == "mock":
        notes.append("Generated by the offline mock model (rule-based); enable Claude for model-written analysis.")
    else:
        notes.append("AI analysis unavailable; this is a deterministic, pattern-based summary.")
    if pack.omitted_group_count:
        notes.append(f"{pack.omitted_group_count} lower-risk event group(s) were not included in the evidence pack.")
    if stats.get("malformed_lines"):
        notes.append(f"{stats['malformed_lines']} line(s) could not be parsed and were only partially analyzed.")
    injected = [i for i in items if i.kind == "prompt_injection"]
    if injected:
        notes.append(
            "Suspected prompt-injection content at "
            + ", ".join(i.line_label() for i in injected[:5])
            + " was withheld from the analysis."
        )

    overall: Confidence = hypotheses[0].confidence if hypotheses else "low"
    return AIAnalysis(
        incident_title=_short(title, 160),
        impact=_short(impact, 500),
        observed_facts=facts,
        hypotheses=hypotheses[:5],
        recommendations=recs,
        critical_evidence_ids=must_ids,
        overall_confidence=overall,
        uncertainty_notes=notes[:6],
    )
