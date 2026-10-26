"""SQLAlchemy ORM models. Portable types: PostgreSQL in production, SQLite in tests."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(16), default="upload")
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(32), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    total_lines: Mapped[int] = mapped_column(Integer, default=0)
    parsed_lines: Mapped[int] = mapped_column(Integer, default=0)
    malformed_lines: Mapped[int] = mapped_column(Integer, default=0)
    stats: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    analysis: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    summary_lines: Mapped[list[str] | None] = mapped_column(JSON)
    ai_status: Mapped[str | None] = mapped_column(String(16))
    ai_provider: Mapped[str | None] = mapped_column(String(32))
    ai_model: Mapped[str | None] = mapped_column(String(64))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    confidence: Mapped[str | None] = mapped_column(String(8))
    redaction_counts: Mapped[dict[str, int] | None] = mapped_column(JSON)
    timings_ms: Mapped[dict[str, float] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    lines: Mapped[list["LogLine"]] = relationship(
        back_populates="analysis_ref", cascade="all, delete-orphan", passive_deletes=True
    )
    groups: Mapped[list["EventGroupRow"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    signals: Mapped[list["SignalRow"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)


class LogLine(Base):
    __tablename__ = "log_lines"
    __table_args__ = (
        Index("ix_log_lines_analysis_line", "analysis_id", "line_no", unique=True),
        Index("ix_log_lines_analysis_severity", "analysis_id", "severity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"))
    line_no: Mapped[int] = mapped_column(Integer)
    ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    severity: Mapped[str] = mapped_column(String(10))
    service: Mapped[str | None] = mapped_column(String(64))
    correlation_id: Mapped[str | None] = mapped_column(String(80))
    message: Mapped[str] = mapped_column(Text)
    raw: Mapped[str] = mapped_column(Text)
    parse_ok: Mapped[bool] = mapped_column(Boolean, default=True)
    is_continuation: Mapped[bool] = mapped_column(Boolean, default=False)
    fingerprint: Mapped[str | None] = mapped_column(String(16))

    analysis_ref: Mapped[Analysis] = relationship(back_populates="lines")


class EventGroupRow(Base):
    __tablename__ = "event_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    fingerprint: Mapped[str] = mapped_column(String(16))
    template: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(10))
    service: Mapped[str | None] = mapped_column(String(64))
    count: Mapped[int] = mapped_column(Integer)
    first_line: Mapped[int] = mapped_column(Integer)
    last_line: Mapped[int] = mapped_column(Integer)
    first_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sample_lines: Mapped[list[int]] = mapped_column(JSON)
    patterns: Mapped[list[str]] = mapped_column(JSON)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    score_breakdown: Mapped[dict[str, int] | None] = mapped_column(JSON)


class SignalRow(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    tags: Mapped[list[str]] = mapped_column(JSON)
    pattern_ids: Mapped[list[str]] = mapped_column(JSON)
    severity: Mapped[str] = mapped_column(String(10))
    service: Mapped[str | None] = mapped_column(String(64))
    line_no: Mapped[int] = mapped_column(Integer)
    line_numbers: Mapped[list[int]] = mapped_column(JSON)
    ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    message: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    must_include: Mapped[bool] = mapped_column(Boolean, default=False)
    group_fingerprint: Mapped[str | None] = mapped_column(String(16))
    count: Mapped[int] = mapped_column(Integer, default=1)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
