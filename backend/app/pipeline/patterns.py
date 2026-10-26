"""Versioned catalog of deterministic incident patterns."""

import re
from dataclasses import dataclass

CATALOG_VERSION = "patterns/v1.0.0"


@dataclass(frozen=True)
class Pattern:
    id: str
    title: str
    category: str
    regex: re.Pattern[str]
    weight: int
    # Cheap lowercase substring prefilter: the regex only runs when one of these occurs in the message.
    keywords: tuple[str, ...] = ()


def _rx(expr: str) -> re.Pattern[str]:
    return re.compile(expr, re.IGNORECASE)


PATTERNS: list[Pattern] = [
    Pattern(
        "pool_exhaustion",
        "Connection pool exhaustion / pressure",
        "database",
        _rx(
            r"(?:connection|conn|db|database|thread|worker)[\s_-]?pool.{0,50}"
            r"(?:exhaust|deplet|no (?:available|idle|free)|reached|usage|saturat|limit|maxed|wait|full|timeout)"
            r"|pool (?:exhausted|is full|saturated)|too many connections|remaining connection slots"
            r"|unable to acquire (?:a )?connection|could not get (?:a )?connection"
        ),
        25,
        ("pool", "too many connections", "connection slots", "acquire", "get a connection", "get connection"),
    ),
    Pattern(
        "db_timeout",
        "Database timeout",
        "database",
        _rx(
            r"(?:database|\bdb\b|sql|postgres|mysql|mongo|query|jdbc|statement).{0,60}(?:timed?[ -]?out|timeout)"
            r"|(?:timed?[ -]?out|timeout).{0,40}(?:database|\bdb\b|query|sql|statement)"
            r"|statement timeout|lock wait timeout|canceling statement due to"
        ),
        20,
        ("time", "canceling statement"),
    ),
    Pattern(
        "auth_failure",
        "Authentication / authorization failure",
        "security",
        _rx(
            r"(?:auth(?:entication|orization)?|login|log-in|sign[- ]?in|credential|password|token|jwt|session)"
            r".{0,40}(?:fail|invalid|denied|expired|rejected|unauthori[sz]ed|mismatch)"
            r"|invalid (?:api key|credentials|token|signature)|\b401 unauthori[sz]ed|\b403 forbidden"
            r"|brute.?force|account (?:locked|lockout)|lockout threshold"
        ),
        15,
        (
            "auth",
            "login",
            "log-in",
            "sign",
            "credential",
            "password",
            "token",
            "jwt",
            "session",
            "invalid",
            "401",
            "403",
            "brute",
            "lock",
        ),
    ),
    Pattern(
        "memory_pressure",
        "Memory pressure / out of memory",
        "resources",
        _rx(
            r"out ?of ?memory|\bOOM\b|oom-?kill|heap (?:space|usage|exhaust|limit)|memory (?:usage|pressure|limit|exceeded|leak)"
            r"|gc overhead|allocation fail|cannot allocate memory|java\.lang\.OutOfMemoryError"
        ),
        25,
        ("memory", "oom", "heap", "gc overhead", "alloc"),
    ),
    Pattern(
        "service_failure",
        "Service failure / unavailability",
        "availability",
        _rx(
            r"service unavailable|(?:status|http|code|responded|returned|response)[^\d\n]{0,15}50[234]\b|\s50[234]\s+\d+(?:\.\d+)?ms\b|bad gateway|gateway timeout|connection refused|circuit.?breaker.{0,20}open"
            r"|upstream.{0,40}(?:fail|unavailable|unhealthy|error)|health ?check.{0,20}fail|\bcrash(?:ed|ing)?\b"
            r"|\bpanic\b|segfault|segmentation fault|unhandled exception|uncaught exception"
            r"|restart(?:ing|ed)? (?:loop|unexpectedly)|crashloopbackoff|exited with code [1-9]"
        ),
        20,
        (
            "unavailable",
            "50",
            "gateway",
            "refused",
            "breaker",
            "upstream",
            "health",
            "crash",
            "panic",
            "segfault",
            "segmentation",
            "unhandled",
            "uncaught",
            "restart",
            "exited",
        ),
    ),
    Pattern(
        "disk_pressure",
        "Disk / filesystem pressure",
        "resources",
        _rx(r"no space left|disk (?:full|usage|quota|pressure)|filesystem.{0,20}(?:full|read-only)|inode"),
        20,
        ("space", "disk", "filesystem", "inode"),
    ),
    Pattern(
        "rate_limit",
        "Rate limiting / throttling",
        "availability",
        _rx(
            r"rate.?limit|too many requests|throttl"
            r"|(?:status|http|code|responded|returned|response)[^\d\n]{0,15}429\b|\s429\s+\d+(?:\.\d+)?ms\b"
        ),
        10,
        ("rate", "too many requests", "429", "throttl"),
    ),
]

PATTERNS_BY_ID: dict[str, Pattern] = {p.id: p for p in PATTERNS}

# A warning in the key category that precedes an error burst in a value category is a likely precursor.
PRECURSOR_LINKS: dict[str, set[str]] = {
    "pool_exhaustion": {"db_timeout", "pool_exhaustion", "service_failure"},
    "memory_pressure": {"memory_pressure", "service_failure"},
    "disk_pressure": {"disk_pressure", "service_failure", "db_timeout"},
    "rate_limit": {"service_failure", "rate_limit"},
    "db_timeout": {"service_failure", "db_timeout"},
    "auth_failure": {"auth_failure"},
}

THRESHOLD_RE = re.compile(
    r"(?P<subject>usage|utili[sz]ation|capacity|reached|used|full|load|pool|memory|heap|cpu|disk|quota)"
    r"[^%\n]{0,40}?(?P<value>\d{2,3}(?:\.\d+)?)\s?%",
    re.IGNORECASE,
)

INJECTION_RE = re.compile(
    r"ignore (?:all |any )?(?:previous|prior|above|earlier|the) (?:instructions|prompts?|rules)"
    r"|disregard (?:all |any )?(?:previous|prior|above|your) (?:instructions|rules|prompts?)"
    r"|you are now (?:a|an|in)\b|new instructions\s*:|system prompt|developer mode"
    r"|</?(?:system|assistant|instructions?|log_evidence)>|respond only with|report that (?:the )?system is healthy"
    r"|as an ai (?:language )?model",
    re.IGNORECASE,
)


def match_patterns(message: str) -> list[str]:
    lowered = message.lower()
    return [p.id for p in PATTERNS if any(k in lowered for k in p.keywords) and p.regex.search(message)]


def threshold_value(message: str) -> float | None:
    best: float | None = None
    for match in THRESHOLD_RE.finditer(message):
        value = float(match["value"])
        if value <= 100 and (best is None or value > best):
            best = value
    return best


def looks_like_injection(message: str) -> bool:
    return bool(INJECTION_RE.search(message))
