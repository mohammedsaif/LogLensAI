"""Normalization helpers: severities, timestamps and message templates (fingerprints)."""

import hashlib
import re
from datetime import UTC, datetime

from app.pipeline.models import Severity

_SEVERITY_ALIASES: dict[str, Severity] = {
    "TRACE": Severity.DEBUG,
    "DEBUG": Severity.DEBUG,
    "DBG": Severity.DEBUG,
    "FINE": Severity.DEBUG,
    "INFO": Severity.INFO,
    "INFORMATION": Severity.INFO,
    "NOTICE": Severity.INFO,
    "WARN": Severity.WARN,
    "WARNING": Severity.WARN,
    "ERR": Severity.ERROR,
    "ERROR": Severity.ERROR,
    "SEVERE": Severity.ERROR,
    "CRIT": Severity.CRITICAL,
    "CRITICAL": Severity.CRITICAL,
    "FATAL": Severity.CRITICAL,
    "ALERT": Severity.CRITICAL,
    "EMERG": Severity.CRITICAL,
    "EMERGENCY": Severity.CRITICAL,
    "PANIC": Severity.CRITICAL,
}

# pino / bunyan numeric levels
_NUMERIC_LEVELS = [
    (60, Severity.CRITICAL),
    (50, Severity.ERROR),
    (40, Severity.WARN),
    (30, Severity.INFO),
    (0, Severity.DEBUG),
]


def normalize_severity(value: object) -> Severity:
    if value is None:
        return Severity.UNKNOWN
    if isinstance(value, bool):
        return Severity.UNKNOWN
    if isinstance(value, int | float):
        for threshold, sev in _NUMERIC_LEVELS:
            if value >= threshold:
                return sev
        return Severity.DEBUG
    return _SEVERITY_ALIASES.get(str(value).strip().upper(), Severity.UNKNOWN)


_FRACTION = re.compile(r"(T\d{2}:\d{2}:\d{2})[.,](\d+)")


def parse_timestamp(value: object, default_year: int | None = None) -> datetime | None:
    """Parse ISO-8601-ish strings, epoch seconds/millis, or syslog 'Mon dd HH:MM:SS'. Returns aware UTC."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        seconds = value / 1000 if value > 1e11 else value
        try:
            return datetime.fromtimestamp(seconds, UTC)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d{10}(\d{3})?(\.\d+)?", text):
        return parse_timestamp(float(text))
    syslog = re.fullmatch(r"([A-Z][a-z]{2})\s+(\d{1,2})\s(\d{2}:\d{2}:\d{2})", text)
    if syslog:
        year = default_year or datetime.now(UTC).year
        try:
            return datetime.strptime(f"{year} {syslog[1]} {syslog[2]} {syslog[3]}", "%Y %b %d %H:%M:%S").replace(
                tzinfo=UTC
            )
        except ValueError:
            return None
    iso = text.replace(" ", "T", 1) if re.match(r"\d{4}-\d{2}-\d{2} \d", text) else text
    iso = iso.replace("Z", "+00:00").replace("z", "+00:00")
    # Normalize the fractional part to exactly 6 digits with a '.' separator.
    iso = _FRACTION.sub(lambda m: f"{m[1]}.{m[2][:6].ljust(6, '0')}", iso, count=1)
    iso = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", iso)
    try:
        parsed = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


_TEMPLATE_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I), "<uuid>"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"), "<ts>"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "<email>"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b"), "<ip>"),
    (re.compile(r"\b0x[0-9a-f]+\b", re.I), "<hex>"),
    (re.compile(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{12,}\b", re.I), "<hex>"),
    # Identifier-like keys are always masked; other key=value tokens only when they look generated (digit or dash).
    (
        re.compile(
            r"\b((?:correlation_id|correlationid|request_id|requestid|trace_id|traceid|span_id|req_id|session_id|id)=)"
            r"[^\s,;&]+",
            re.I,
        ),
        r"\1<id>",
    ),
    (re.compile(r"(?<==)(?=[A-Za-z0-9_-]*[\d-])[A-Za-z0-9_-]+"), "<id>"),
    (re.compile(r"\"[^\"]{1,200}\"|'[^']{1,200}'"), '"<str>"'),
    (re.compile(r"(?<![A-Za-z<])\d+(?:\.\d+)?(?=(?:ms|s|m|h|%|kb|mb|gb|b)?\b)", re.I), "<n>"),
]


def make_template(message: str) -> str:
    template = message.strip()
    for pattern, repl in _TEMPLATE_RULES:
        template = pattern.sub(repl, template)
    template = re.sub(r"\s+", " ", template)
    return template[:300]


def make_fingerprint(severity: str, service: str | None, template: str) -> str:
    key = f"{severity}|{service or '-'}|{template}"
    return hashlib.sha1(key.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
