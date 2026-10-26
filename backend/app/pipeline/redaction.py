"""Redaction of credentials, tokens and personal data before any external model call."""

import re
from collections import Counter
from collections.abc import Callable


def _luhn_ok(digits: str) -> bool:
    total, parity = 0, len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _card(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match[0])
    return "[REDACTED_CARD]" if 13 <= len(digits) <= 19 and _luhn_ok(digits) else match[0]


# Regex of key *names* whose values are secrets (not a secret itself).
_SENSITIVE_FIELDS = (
    r"api[_-]?key|apikey|x-api-key|access[_-]?token|refresh[_-]?token|auth[_-]?token|id[_-]?token|secret|client[_-]?secret"
    r"|password|passwd|pwd|passphrase|private[_-]?key|session[_-]?(?:id|token)|cookie|set-cookie|token"
)

# (category, pattern, replacement). Order matters: the most specific patterns run first.
_RULES: list[tuple[str, re.Pattern[str], str | Callable[[re.Match[str]], str]]] = [
    (
        "private_key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", re.S),
        "[REDACTED_PRIVATE_KEY]",
    ),
    ("url_credentials", re.compile(r"\b([a-z][a-z0-9+.-]*://)[^\s:/@]+:[^\s@/]+@", re.I), r"\1[REDACTED_CREDENTIALS]@"),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b"), "[REDACTED_JWT]"),
    ("bearer_token", re.compile(r"\b(Bearer|Basic|Token)\s+[A-Za-z0-9\-._~+/]{8,}=*", re.I), r"\1 [REDACTED_TOKEN]"),
    (
        "api_key",
        re.compile(
            r"\b(?:sk-(?:ant-)?[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,}"
            r"|xox[abprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35}|sk_live_[0-9A-Za-z]{16,}|rk_live_[0-9A-Za-z]{16,})\b"
        ),
        "[REDACTED_API_KEY]",
    ),
    (
        "secret_assignment",
        re.compile(rf"(?i)(\b(?:{_SENSITIVE_FIELDS})\b\"?\s*[=:]\s*\"?)(?!\[REDACTED)[^\s,\"';&}}]+"),
        r"\1[REDACTED_SECRET]",
    ),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED_EMAIL]"),
    ("card_number", re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])"), _card),
]

_IPV4 = (
    "ip_address",
    re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"),
    "[REDACTED_IP]",
)


class Redactor:
    def __init__(self, redact_ips: bool = True):
        self.rules = list(_RULES) + ([_IPV4] if redact_ips else [])
        self.counts: Counter[str] = Counter()

    def redact(self, text: str) -> str:
        for category, pattern, repl in self.rules:
            if callable(repl):
                # Callable replacements may keep the original text (e.g. failed Luhn check); count real hits only.
                hits = 0

                def _counted(m: re.Match[str], _repl: Callable[[re.Match[str]], str] = repl) -> str:
                    nonlocal hits
                    out = _repl(m)
                    hits += out != m[0]
                    return out

                text = pattern.sub(_counted, text)
                n = hits
            else:
                text, n = pattern.subn(repl, text)
            if n:
                self.counts[category] += n
        return text


def redact(text: str, redact_ips: bool = True) -> tuple[str, dict[str, int]]:
    redactor = Redactor(redact_ips)
    return redactor.redact(text), dict(redactor.counts)
