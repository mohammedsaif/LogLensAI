"""Deterministic statistics: counts, services, time range, timeline buckets, parse quality."""

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from app.pipeline.models import EventGroup, LogRecord, Severity

_BUCKET_SIZES = [1, 5, 10, 30, 60, 300, 900, 1800, 3600, 6 * 3600, 86400]
TARGET_BUCKETS = 40


def _bucket_seconds(span_seconds: float) -> int:
    for size in _BUCKET_SIZES:
        if span_seconds / size <= TARGET_BUCKETS:
            return size
    return _BUCKET_SIZES[-1]


def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z") if dt else None


def compute_stats(records: list[LogRecord], groups: list[EventGroup]) -> dict[str, Any]:
    events = [r for r in records if r.is_event]
    severity = Counter(r.severity for r in events)
    services = Counter(r.service for r in events if r.service)
    error_services = Counter(
        r.service for r in events if r.service and r.severity in (Severity.ERROR, Severity.CRITICAL)
    )
    formats = Counter(r.fmt for r in records)
    pattern_counts: Counter[str] = Counter()
    for r in events:
        pattern_counts.update(r.patterns)

    timestamps = [r.ts for r in events if r.ts is not None]
    start = min(timestamps) if timestamps else None
    end = max(timestamps) if timestamps else None

    timeline: list[dict[str, Any]] = []
    bucket_size = 0
    if start and end:
        span = max((end - start).total_seconds(), 1)
        bucket_size = _bucket_seconds(span)
        epoch0 = int(start.timestamp()) // bucket_size * bucket_size
        n_buckets = int((end.timestamp() - epoch0) // bucket_size) + 1
        buckets = [Counter() for _ in range(n_buckets)]
        for r in events:
            if r.ts is not None:
                buckets[int((r.ts.timestamp() - epoch0) // bucket_size)][r.severity] += 1
        for idx, counter in enumerate(buckets):
            timeline.append(
                {
                    "t": _iso(datetime.fromtimestamp(epoch0, UTC) + timedelta(seconds=idx * bucket_size)),
                    **{sev.value: counter.get(sev.value, 0) for sev in Severity},
                    "total": sum(counter.values()),
                }
            )

    duplicate_groups = [g for g in groups if g.count > 1]
    return {
        "total_lines": len(records),
        "event_count": len(events),
        "blank_lines": formats.get("blank", 0),
        "continuation_lines": sum(1 for r in records if r.is_continuation),
        "parsed_lines": sum(1 for r in events if r.parse_ok),
        "malformed_lines": sum(1 for r in events if not r.parse_ok),
        "formats": dict(formats),
        "severity_counts": {sev.value: severity.get(sev.value, 0) for sev in Severity},
        "errors": severity.get(Severity.ERROR, 0),
        "warnings": severity.get(Severity.WARN, 0),
        "critical": severity.get(Severity.CRITICAL, 0),
        "services": [
            {"name": name, "count": count, "errors": error_services.get(name, 0)}
            for name, count in services.most_common()
        ],
        "affected_services": sorted(error_services),
        "time_range": {
            "start": _iso(start),
            "end": _iso(end),
            "duration_seconds": int((end - start).total_seconds()) if start and end else None,
        },
        "timeline": timeline,
        "timeline_bucket_seconds": bucket_size,
        "pattern_counts": dict(pattern_counts.most_common()),
        "group_count": len(groups),
        "duplicate_group_count": len(duplicate_groups),
        "duplicate_event_count": sum(g.count - 1 for g in duplicate_groups),
        "with_correlation_id": sum(1 for r in events if r.correlation_id),
    }
