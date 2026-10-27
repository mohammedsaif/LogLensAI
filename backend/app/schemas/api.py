"""Request/response models for the public REST API."""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


def _as_utc(value: datetime | None) -> datetime | None:
    # SQLite returns naive datetimes; everything LogLens stores is UTC, so make that explicit on the wire.
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


UTCDateTime = Annotated[datetime, AfterValidator(_as_utc)]


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class AnalysisStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    filename: str
    status: Literal["queued", "processing", "completed", "failed"]
    stage: str
    progress: int
    error_code: str | None = None
    error_message: str | None = None
    created_at: UTCDateTime
    completed_at: UTCDateTime | None = None


class AnalysisListItem(AnalysisStatusOut):
    source: str
    size_bytes: int
    total_lines: int
    ai_status: str | None = None
    ai_provider: str | None = None
    confidence: str | None = None
    errors: int = 0
    warnings: int = 0
    critical: int = 0
    incident_title: str | None = None


class AnalysisListOut(BaseModel):
    items: list[AnalysisListItem]
    total: int
    limit: int
    offset: int


class EventGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    fingerprint: str
    template: str
    severity: str
    service: str | None
    count: int
    first_line: int
    last_line: int
    first_ts: UTCDateTime | None
    last_ts: UTCDateTime | None
    sample_lines: list[int]
    patterns: list[str]
    risk_score: int
    score_breakdown: dict[str, int] | None = None


class SignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    kind: str
    tags: list[str]
    pattern_ids: list[str]
    severity: str
    service: str | None
    line_no: int
    line_numbers: list[int]
    ts: UTCDateTime | None
    message: str
    reason: str
    must_include: bool
    count: int
    risk_score: int


class AnalysisDetailOut(AnalysisListItem):
    parsed_lines: int
    malformed_lines: int
    ai_model: str | None = None
    prompt_version: str | None = None
    summary_lines: list[str] | None = None
    analysis: dict[str, Any] | None = None
    evidence: dict[str, Any] | None = None
    stats: dict[str, Any] | None = None
    redaction_counts: dict[str, int] | None = None
    timings_ms: dict[str, float] | None = None
    signals: list[SignalOut] = Field(default_factory=list)
    groups: list[EventGroupOut] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)


class LogLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    line_no: int
    ts: UTCDateTime | None
    severity: str
    service: str | None
    correlation_id: str | None
    message: str
    raw: str
    parse_ok: bool
    is_continuation: bool


class LinesPageOut(BaseModel):
    items: list[LogLineOut]
    total: int
    page: int
    page_size: int


class SampleRequest(BaseModel):
    scenario: Literal["pool_exhaustion", "auth_attack", "memory_leak", "healthy", "prompt_injection"] = (
        "pool_exhaustion"
    )
    lines: int = Field(default=1000, ge=50, le=50_000)
    format: Literal["text", "jsonl"] = "text"
    seed: int = Field(default=42, ge=0, le=2**31)


class ScenarioOut(BaseModel):
    id: str
    description: str


class ConfigOut(BaseModel):
    app_name: str
    version: str
    environment: str
    ai_provider: str
    ai_model: str
    ai_mode_label: str
    ai_external: bool = False  # True when redacted evidence is sent to a third-party AI service
    prompt_version: str
    ai_timeout_seconds: float
    ai_max_retries: int
    evidence_token_budget: int
    max_upload_mb: float
    max_lines: int
    allowed_extensions: list[str]
    retention_days: int
    redaction_enabled: bool
    redact_ip_addresses: bool
    scenarios: list[ScenarioOut]
