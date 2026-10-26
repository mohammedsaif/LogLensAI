"""Duplicate detection: group events by (severity, service, message template)."""

from app.pipeline.models import SEVERITY_RANK, EventGroup, LogRecord
from app.pipeline.normalize import make_fingerprint, make_template
from app.pipeline.patterns import match_patterns, threshold_value


def enrich_records(records: list[LogRecord]) -> None:
    """Compute template, fingerprint and pattern matches for each event record (in place)."""
    # Duplicate messages are common, so template + pattern results are cached per exact message.
    cache: dict[str, tuple[str, list[str]]] = {}
    for record in records:
        if not record.is_event:
            continue
        cached = cache.get(record.message)
        if cached is None:
            # Patterns are matched on the raw message (templates mask numbers such as HTTP status codes).
            cached = (make_template(record.message), match_patterns(record.message))
            if len(cache) < 100_000:
                cache[record.message] = cached
        record.template, record.patterns = cached
        record.fingerprint = make_fingerprint(record.severity, record.service, record.template)


def aggregate(records: list[LogRecord]) -> list[EventGroup]:
    groups: dict[str, EventGroup] = {}
    for record in records:
        if not record.is_event:
            continue
        group = groups.get(record.fingerprint)
        if group is None:
            group = EventGroup(
                fingerprint=record.fingerprint,
                template=record.template,
                severity=record.severity,
                service=record.service,
                first_line=record.line_no,
                first_ts=record.ts,
                example_message=record.message,
            )
            groups[record.fingerprint] = group
        group.count += 1
        group.last_line = record.line_no
        group.line_numbers.append(record.line_no)
        if record.ts is not None:
            if group.first_ts is None or record.ts < group.first_ts:
                group.first_ts = record.ts
            if group.last_ts is None or record.ts > group.last_ts:
                group.last_ts = record.ts
        if "%" in record.message:
            value = threshold_value(record.message)
            if value is not None and (group.peak_percent is None or value > group.peak_percent):
                group.peak_percent, group.peak_line = value, record.line_no
        for pid in record.patterns:
            if pid not in group.patterns:
                group.patterns.append(pid)
    return sorted(groups.values(), key=lambda g: (-SEVERITY_RANK.get(g.severity, 0), -g.count, g.first_line))
