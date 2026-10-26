"""Core data structures shared by pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Severity(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


SEVERITY_RANK: dict[str, int] = {
    Severity.DEBUG: 0,
    Severity.INFO: 1,
    Severity.UNKNOWN: 1,
    Severity.WARN: 2,
    Severity.ERROR: 3,
    Severity.CRITICAL: 4,
}


def is_high_severity(severity: str) -> bool:
    return SEVERITY_RANK.get(severity, 0) >= SEVERITY_RANK[Severity.WARN]


@dataclass(slots=True)
class LogRecord:
    """One physical line of the uploaded file, normalized. Raw text is always preserved."""

    line_no: int
    raw: str
    fmt: str  # json | text | blank | unparsed
    ts: datetime | None = None
    severity: str = Severity.UNKNOWN
    service: str | None = None
    message: str = ""
    correlation_id: str | None = None
    parse_ok: bool = True
    is_continuation: bool = False
    template: str = ""
    fingerprint: str = ""
    patterns: list[str] = field(default_factory=list)

    @property
    def is_event(self) -> bool:
        """Counted as a standalone event (not blank, not a stack-trace continuation)."""
        return self.fmt != "blank" and not self.is_continuation


@dataclass(slots=True)
class EventGroup:
    fingerprint: str
    template: str
    severity: str
    service: str | None
    count: int = 0
    first_line: int = 0
    last_line: int = 0
    first_ts: datetime | None = None
    last_ts: datetime | None = None
    line_numbers: list[int] = field(default_factory=list)
    example_message: str = ""
    patterns: list[str] = field(default_factory=list)
    peak_percent: float | None = None
    peak_line: int | None = None
    risk_score: int = 0
    score_breakdown: dict[str, int] = field(default_factory=dict)

    def sample_lines(self, head: int = 5, tail: int = 2) -> list[int]:
        if len(self.line_numbers) <= head + tail:
            return list(self.line_numbers)
        return self.line_numbers[:head] + self.line_numbers[-tail:]


class SignalKind(StrEnum):
    CRITICAL = "critical"
    PRECURSOR = "precursor"
    THRESHOLD = "threshold"
    RARE_HIGH_SEVERITY = "rare_high_severity"
    PATTERN = "pattern"
    PROMPT_INJECTION = "prompt_injection"


SIGNAL_PRIORITY = [
    SignalKind.CRITICAL,
    SignalKind.PRECURSOR,
    SignalKind.THRESHOLD,
    SignalKind.RARE_HIGH_SEVERITY,
    SignalKind.PATTERN,
    SignalKind.PROMPT_INJECTION,
]


class Signal(BaseModel):
    """A deterministically detected signal. must_include signals are guaranteed to reach the final analysis."""

    kind: SignalKind
    tags: list[SignalKind] = Field(default_factory=list)
    severity: str
    line_no: int
    line_numbers: list[int] = Field(default_factory=list)
    ts: datetime | None = None
    service: str | None = None
    message: str
    reasons: list[str] = Field(default_factory=list)
    pattern_ids: list[str] = Field(default_factory=list)
    must_include: bool = False
    group_fingerprint: str | None = None
    count: int = 1
    risk_score: int = 0

    @property
    def reason(self) -> str:
        return "; ".join(self.reasons)
