"""Best-effort log parser for JSON lines and common text formats.

Every physical line becomes a LogRecord with its original 1-based line number and raw text,
including lines that cannot be parsed (parse_ok=False). Log content is treated purely as data.
"""

import json
import re
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from app.pipeline.models import LogRecord, Severity
from app.pipeline.normalize import normalize_severity, parse_timestamp

MAX_RAW_CHARS = 10_000

_LEVEL_WORDS = r"TRACE|DEBUG|DBG|INFO|INFORMATION|NOTICE|WARN(?:ING)?|ERR(?:OR)?|SEVERE|CRIT(?:ICAL)?|FATAL|ALERT|EMERG(?:ENCY)?|PANIC"

_ISO_TS = r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d{1,9})?(?:Z|[+-]\d{2}:?\d{2})?"
_SYSLOG_TS = r"[A-Z][a-z]{2}\s+\d{1,2}\s\d{2}:\d{2}:\d{2}"

RE_LEADING_TS = re.compile(rf"^\s*[\[(]?(?P<ts>{_ISO_TS}|{_SYSLOG_TS})[\])]?\s*")
RE_LEVEL_HEAD = re.compile(rf"^[\[(<]?(?P<level>{_LEVEL_WORDS})[\])>]?(?::|\s|$)\s*", re.IGNORECASE)
RE_LEVEL_KV = re.compile(rf"\b(?:level|lvl|severity)=\"?(?P<level>{_LEVEL_WORDS})\b", re.IGNORECASE)
RE_LEVEL_ANYWHERE = re.compile(rf"(?<![\w-])(?P<level>{_LEVEL_WORDS})(?![\w-])")
RE_SERVICE_BRACKET = re.compile(r"^\[(?P<svc>[A-Za-z][\w.\-/:]{0,63})\]\s*[:\-]?\s*")
# "svc[123]: msg" or "order-service: msg" (token must carry a pid or a separator, so "Connection: ..." is not a service)
RE_SERVICE_COLON = re.compile(
    r"^(?P<svc>[A-Za-z][\w]*[.\-/_][\w.\-/]{0,60}|[A-Za-z][\w.\-/]{0,63}(?=\[\d+\]))(?:\[\d+\])?:\s+"
)
RE_SERVICE_DASH = re.compile(r"^(?P<svc>[a-z][\w.\-]{0,63})\s+-\s+")
RE_SERVICE_KV = re.compile(r"\b(?:service|svc|app|component)=\"?(?P<svc>[\w.\-/]{1,64})", re.IGNORECASE)
RE_SYSLOG_HOST_SVC = re.compile(r"^(?P<host>\S+)\s+(?P<svc>[A-Za-z][\w.\-/]{0,63})(?:\[\d+\])?:\s*")
RE_CORRELATION = re.compile(
    r"\b(?:correlation[_-]?id|corr(?:elation)?(?:Id)?|trace[_-]?id|request[_-]?id|req[_-]?id|x-request-id)"
    r"\s*[=:]\s*\"?(?P<cid>[\w\-:.]{4,80})",
    re.IGNORECASE,
)
RE_CONTINUATION = re.compile(
    r"^(?:\s+\S|\s*at\s+[\w$.<>]+\(|Traceback \(most recent call last\)|Caused by:|\s*\.\.\. \d+ more)"
)

# Final line of a Python traceback, e.g. "ValueError: card declined" (only after other continuation lines).
RE_EXCEPTION_END = re.compile(r"^[A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt)\b(?::|$)")

_JSON_KEYS: dict[str, tuple[str, ...]] = {
    "ts": ("timestamp", "@timestamp", "ts", "time", "datetime", "date", "eventtime"),
    "level": ("level", "severity", "lvl", "loglevel", "log.level", "levelname"),
    "service": ("service", "service.name", "service_name", "app", "application", "logger", "component", "source"),
    "message": ("message", "msg", "event", "log", "text", "error.message"),
    "cid": (
        "correlation_id",
        "correlationid",
        "trace_id",
        "traceid",
        "request_id",
        "requestid",
        "x-request-id",
        "span_id",
    ),
}


def _lookup(obj: dict[str, Any], keys: tuple[str, ...]) -> Any:
    lowered = {k.lower(): v for k, v in obj.items()}
    for key in keys:
        if key in lowered:
            return lowered[key]
        if "." in key:
            head, tail = key.split(".", 1)
            nested = lowered.get(head)
            if isinstance(nested, dict):
                value = _lookup(nested, (tail,))
                if value is not None:
                    return value
    return None


def _parse_json(record: LogRecord, obj: dict[str, Any], default_year: int | None) -> None:
    record.fmt = "json"
    record.ts = parse_timestamp(_lookup(obj, _JSON_KEYS["ts"]), default_year)
    level = _lookup(obj, _JSON_KEYS["level"])
    record.severity = normalize_severity(level)
    service = _lookup(obj, _JSON_KEYS["service"])
    if isinstance(service, dict):
        service = service.get("name")
    record.service = str(service)[:64] if service not in (None, "") else None
    message = _lookup(obj, _JSON_KEYS["message"])
    if message is None:
        used = {k for group in _JSON_KEYS.values() for k in group}
        rest = {k: v for k, v in obj.items() if k.lower() not in used}
        message = json.dumps(rest, ensure_ascii=False, default=str) if rest else ""
    record.message = str(message)
    cid = _lookup(obj, _JSON_KEYS["cid"])
    if cid is None:
        match = RE_CORRELATION.search(record.message)
        cid = match["cid"] if match else None
    record.correlation_id = str(cid)[:80] if cid not in (None, "") else None
    # A JSON object without any recognizable log fields is still preserved but flagged.
    record.parse_ok = record.ts is not None or record.severity != Severity.UNKNOWN or bool(record.message)


def _parse_text(record: LogRecord, line: str, default_year: int | None) -> None:
    record.fmt = "text"
    rest = line.strip()
    is_syslog = False
    ts_match = RE_LEADING_TS.match(rest)
    if ts_match:
        record.ts = parse_timestamp(ts_match["ts"], default_year)
        is_syslog = not ts_match["ts"][0].isdigit()
        rest = rest[ts_match.end() :]

    if is_syslog:
        hs = RE_SYSLOG_HOST_SVC.match(rest)
        if hs:
            record.service = hs["svc"]
            rest = rest[hs.end() :]

    level_match = RE_LEVEL_HEAD.match(rest)
    if level_match:
        record.severity = normalize_severity(level_match["level"])
        rest = rest[level_match.end() :]
    else:
        kv = RE_LEVEL_KV.search(rest)
        if kv:
            record.severity = normalize_severity(kv["level"])
        else:
            # Only trust an upper-case level word near the start, to avoid "retrying after error" style false hits.
            anywhere = RE_LEVEL_ANYWHERE.search(rest[:48])
            if anywhere and anywhere["level"].isupper():
                record.severity = normalize_severity(anywhere["level"])
                rest = (rest[: anywhere.start()] + rest[anywhere.end() :]).strip()

    if record.service is None:
        for pattern in (RE_SERVICE_BRACKET, RE_SERVICE_COLON, RE_SERVICE_DASH):
            svc = pattern.match(rest)
            if svc:
                record.service = svc["svc"]
                rest = rest[svc.end() :]
                break
        else:
            kv_svc = RE_SERVICE_KV.search(rest)
            if kv_svc:
                record.service = kv_svc["svc"]

    record.message = rest.strip(" -:|") or line.strip()
    cid = RE_CORRELATION.search(line)
    record.correlation_id = cid["cid"] if cid else None
    record.parse_ok = record.ts is not None or record.severity != Severity.UNKNOWN


def parse_line(
    line_no: int, line: str, previous: LogRecord | None = None, default_year: int | None = None
) -> LogRecord:
    raw = line.rstrip("\r\n")
    if len(raw) > MAX_RAW_CHARS:
        raw = raw[:MAX_RAW_CHARS] + " …[truncated]"
    record = LogRecord(line_no=line_no, raw=raw, fmt="unparsed")
    if not raw.strip():
        record.fmt = "blank"
        record.message = ""
        return record

    stripped = raw.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            obj = json.loads(stripped)
        except (json.JSONDecodeError, RecursionError):
            obj = None
        if isinstance(obj, dict):
            _parse_json(record, obj, default_year)
            return record

    continues = RE_CONTINUATION.match(raw) or (
        previous is not None and previous.is_continuation and RE_EXCEPTION_END.match(raw)
    )
    if previous is not None and previous.fmt != "blank" and continues and not RE_LEADING_TS.match(raw):
        record.fmt = "text"
        record.is_continuation = True
        record.ts = previous.ts
        record.severity = previous.severity
        record.service = previous.service
        record.correlation_id = previous.correlation_id
        record.message = stripped
        record.parse_ok = True
        return record

    _parse_text(record, raw, default_year)
    if not record.parse_ok:
        record.fmt = "unparsed"
        record.message = stripped
    return record


def parse_lines(lines: Iterable[str], default_year: int | None = None) -> list[LogRecord]:
    records: list[LogRecord] = []
    previous: LogRecord | None = None
    for idx, line in enumerate(lines, start=1):
        record = parse_line(idx, line, previous, default_year)
        records.append(record)
        if record.fmt != "blank":
            previous = record
    return records


def parse_text(text: str, default_year: int | None = None) -> list[LogRecord]:
    return parse_lines(text.splitlines(), default_year or datetime.now().year)
