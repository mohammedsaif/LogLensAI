"""Incident service: runs an analysis end to end and owns persistence."""

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import anyio
from sqlalchemy import delete, func, insert, or_, select, update
from sqlalchemy.orm import Session

from app.ai.analyzer import analyze
from app.ai.providers.base import AIProvider
from app.ai.providers.factory import get_provider
from app.ai.summary import render_summary
from app.core.config import Settings
from app.core.errors import NotFoundError
from app.db.models import Analysis, EventGroupRow, LogLine, SignalRow
from app.db.session import Database
from app.pipeline.orchestrator import PipelineResult, run_pipeline

log = logging.getLogger("loglens.incidents")
INSERT_CHUNK = 5000


class IncidentService:
    def __init__(
        self, db: Database, settings: Settings, provider_factory: Callable[[Settings], AIProvider | None] = get_provider
    ):
        self.db = db
        self.settings = settings
        self.provider_factory = provider_factory

    # ---- lifecycle -------------------------------------------------------------------------------------------
    def create(self, filename: str, size_bytes: int, source: str, total_lines: int) -> Analysis:
        row = Analysis(
            id=uuid.uuid4().hex,
            filename=filename,
            size_bytes=size_bytes,
            source=source,
            status="queued",
            stage="queued",
            progress=0,
            total_lines=total_lines,
        )
        with self.db.session() as session:
            session.add(row)
            session.commit()
        return row

    def _update(self, analysis_id: str, **fields: Any) -> None:
        with self.db.session() as session:
            session.execute(update(Analysis).where(Analysis.id == analysis_id).values(**fields))
            session.commit()

    async def process(self, analysis_id: str, text: str) -> None:
        """Background task: never raises; failures are recorded on the analysis row."""
        try:
            self._update(analysis_id, status="processing", stage="validating", progress=5)

            def progress(stage: str, pct: int) -> None:
                self._update(analysis_id, stage=stage, progress=pct)

            result: PipelineResult = await anyio.to_thread.run_sync(run_pipeline, text, self.settings, progress)
            self._update(analysis_id, stage="saving_lines", progress=65)
            await anyio.to_thread.run_sync(self._save_pipeline, analysis_id, result)

            self._update(analysis_id, stage="ai_analysis", progress=75)
            provider = self.provider_factory(self.settings)
            incident = await analyze(result.evidence, provider, self.settings)
            summary = render_summary(incident, result.evidence, result.stats)

            self._update(
                analysis_id,
                status="completed",
                stage="completed",
                progress=100,
                total_lines=result.stats["total_lines"],
                parsed_lines=result.stats["parsed_lines"],
                malformed_lines=result.stats["malformed_lines"],
                stats=result.stats,
                evidence=result.evidence.model_dump(mode="json"),
                analysis=incident.model_dump(mode="json"),
                summary_lines=summary,
                ai_status=incident.ai_status,
                ai_provider=incident.provider,
                ai_model=incident.model,
                prompt_version=incident.prompt_version,
                confidence=incident.overall_confidence,
                redaction_counts=result.evidence.redaction_counts,
                timings_ms=result.timings_ms,
                completed_at=datetime.now(UTC),
            )
            log.info(
                "analysis_completed",
                extra={
                    "analysis_id": analysis_id,
                    "ai_status": incident.ai_status,
                    "lines": result.stats["total_lines"],
                },
            )
        except Exception as exc:  # noqa: BLE001 - background task boundary
            log.exception("analysis_failed", extra={"analysis_id": analysis_id})
            self._update(
                analysis_id,
                status="failed",
                stage="failed",
                error_code="PIPELINE_ERROR",
                error_message=f"Processing failed ({type(exc).__name__}). See server logs for details.",
                completed_at=datetime.now(UTC),
            )

    def _save_pipeline(self, analysis_id: str, result: PipelineResult) -> None:
        with self.db.session() as session:
            rows = [
                {
                    "analysis_id": analysis_id,
                    "line_no": r.line_no,
                    "ts": r.ts,
                    "severity": r.severity,
                    "service": r.service,
                    "correlation_id": r.correlation_id,
                    "message": r.message,
                    "raw": r.raw,
                    "parse_ok": r.parse_ok,
                    "is_continuation": r.is_continuation,
                    "fingerprint": r.fingerprint or None,
                }
                for r in result.records
                if r.fmt != "blank"
            ]
            for i in range(0, len(rows), INSERT_CHUNK):
                session.execute(insert(LogLine), rows[i : i + INSERT_CHUNK])
            if result.groups:
                session.execute(
                    insert(EventGroupRow),
                    [
                        {
                            "analysis_id": analysis_id,
                            "fingerprint": g.fingerprint,
                            "template": g.template,
                            "severity": g.severity,
                            "service": g.service,
                            "count": g.count,
                            "first_line": g.first_line,
                            "last_line": g.last_line,
                            "first_ts": g.first_ts,
                            "last_ts": g.last_ts,
                            "sample_lines": g.sample_lines(),
                            "patterns": g.patterns,
                            "risk_score": g.risk_score,
                            "score_breakdown": g.score_breakdown,
                        }
                        for g in result.groups
                    ],
                )
            if result.signals:
                session.execute(
                    insert(SignalRow),
                    [
                        {
                            "analysis_id": analysis_id,
                            "kind": s.kind.value,
                            "tags": [t.value for t in s.tags],
                            "pattern_ids": s.pattern_ids,
                            "severity": s.severity,
                            "service": s.service,
                            "line_no": s.line_no,
                            "line_numbers": s.line_numbers,
                            "ts": s.ts,
                            "message": s.message,
                            "reason": s.reason,
                            "must_include": s.must_include,
                            "group_fingerprint": s.group_fingerprint,
                            "count": s.count,
                            "risk_score": s.risk_score,
                        }
                        for s in result.signals
                    ],
                )
            session.commit()

    # ---- queries ---------------------------------------------------------------------------------------------
    def get(self, session: Session, analysis_id: str) -> Analysis:
        row = session.get(Analysis, analysis_id)
        if row is None:
            raise NotFoundError("Analysis")
        return row

    def list_analyses(self, session: Session, limit: int, offset: int) -> tuple[list[Analysis], int]:
        total = session.scalar(select(func.count()).select_from(Analysis)) or 0
        rows = session.scalars(select(Analysis).order_by(Analysis.created_at.desc()).limit(limit).offset(offset)).all()
        return list(rows), total

    def delete(self, session: Session, analysis_id: str) -> None:
        self.get(session, analysis_id)
        for model in (LogLine, EventGroupRow, SignalRow):
            session.execute(delete(model).where(model.analysis_id == analysis_id))
        session.execute(delete(Analysis).where(Analysis.id == analysis_id))
        session.commit()

    def groups(self, session: Session, analysis_id: str, limit: int = 50) -> list[EventGroupRow]:
        stmt = (
            select(EventGroupRow)
            .where(EventGroupRow.analysis_id == analysis_id)
            .order_by(EventGroupRow.risk_score.desc(), EventGroupRow.first_line)
            .limit(limit)
        )
        return list(session.scalars(stmt).all())

    def signals(self, session: Session, analysis_id: str) -> list[SignalRow]:
        stmt = (
            select(SignalRow)
            .where(SignalRow.analysis_id == analysis_id)
            .order_by(SignalRow.must_include.desc(), SignalRow.risk_score.desc(), SignalRow.line_no)
        )
        return list(session.scalars(stmt).all())

    def query_lines(
        self,
        session: Session,
        analysis_id: str,
        *,
        q: str | None = None,
        severities: list[str] | None = None,
        service: str | None = None,
        malformed_only: bool = False,
        line_numbers: list[int] | None = None,
        around_line: int | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        self.get(session, analysis_id)
        conditions = [LogLine.analysis_id == analysis_id]
        if q:
            # Plain substring search; the value is bound as a parameter (no SQL injection) and LIKE wildcards are escaped.
            escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            conditions.append(or_(LogLine.message.ilike(pattern, escape="\\"), LogLine.raw.ilike(pattern, escape="\\")))
        if severities:
            conditions.append(LogLine.severity.in_(severities))
        if service:
            conditions.append(LogLine.service == service)
        if malformed_only:
            conditions.append(LogLine.parse_ok.is_(False))
        if line_numbers:
            conditions.append(LogLine.line_no.in_(line_numbers))

        total = session.scalar(select(func.count()).select_from(LogLine).where(*conditions)) or 0
        if around_line is not None:
            before = (
                session.scalar(
                    select(func.count()).select_from(LogLine).where(*conditions, LogLine.line_no < around_line)
                )
                or 0
            )
            page = before // page_size + 1
        rows = session.scalars(
            select(LogLine).where(*conditions).order_by(LogLine.line_no).limit(page_size).offset((page - 1) * page_size)
        ).all()
        return {"items": list(rows), "total": total, "page": page, "page_size": page_size}

    def services(self, session: Session, analysis_id: str) -> list[str]:
        stmt = (
            select(LogLine.service).where(LogLine.analysis_id == analysis_id, LogLine.service.is_not(None)).distinct()
        )
        return sorted(s for s in session.scalars(stmt).all() if s)

    # ---- maintenance -----------------------------------------------------------------------------------------
    def mark_interrupted(self) -> int:
        with self.db.session() as session:
            result = session.execute(
                update(Analysis)
                .where(Analysis.status.in_(["queued", "processing"]))
                .values(
                    status="failed",
                    stage="failed",
                    error_code="INTERRUPTED",
                    error_message="The server restarted before this analysis finished. Please upload again.",
                )
            )
            session.commit()
            return result.rowcount or 0

    def purge_expired(self) -> int:
        if self.settings.retention_days <= 0:
            return 0
        cutoff = datetime.now(UTC) - timedelta(days=self.settings.retention_days)
        with self.db.session() as session:
            ids = list(session.scalars(select(Analysis.id).where(Analysis.created_at < cutoff)).all())
            for analysis_id in ids:
                self.delete(session, analysis_id)
            return len(ids)
