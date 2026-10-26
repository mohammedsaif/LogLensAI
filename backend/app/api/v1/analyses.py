"""Analysis endpoints: upload, status, detail, history, raw lines, export, delete."""

from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_service, get_settings_dep
from app.core.config import Settings
from app.core.errors import AppError
from app.db.models import Analysis
from app.pipeline.validation import validate_upload
from app.schemas.api import (
    AnalysisDetailOut,
    AnalysisListItem,
    AnalysisListOut,
    AnalysisStatusOut,
    ErrorResponse,
    EventGroupOut,
    LinesPageOut,
    LogLineOut,
    SignalOut,
)
from app.services.export_service import export_json, export_markdown
from app.services.incident_service import IncidentService

router = APIRouter(prefix="/analyses", tags=["analyses"])

ServiceDep = Annotated[IncidentService, Depends(get_service)]
SessionDep = Annotated[Session, Depends(get_db_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
ERRORS = {code: {"model": ErrorResponse} for code in (400, 404, 413, 415, 422)}


def _list_item(row: Analysis) -> AnalysisListItem:
    stats = row.stats or {}
    item = AnalysisListItem.model_validate(row)
    item.errors = stats.get("errors", 0)
    item.warnings = stats.get("warnings", 0)
    item.critical = stats.get("critical", 0)
    item.incident_title = (row.analysis or {}).get("incident_title")
    return item


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=AnalysisStatusOut, responses=ERRORS)
async def create_analysis(
    background: BackgroundTasks,
    service: ServiceDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File(description=".log, .txt or .jsonl file")],
) -> AnalysisStatusOut:
    """Upload a log file. Returns immediately (202); poll `/analyses/{id}/status` for progress."""
    data = await file.read(settings.max_upload_bytes + 1)
    upload = validate_upload(file.filename, data, settings)
    row = service.create(upload.filename, upload.size_bytes, "upload", upload.line_count)
    background.add_task(service.process, row.id, upload.text)
    return AnalysisStatusOut.model_validate(row)


@router.get("", response_model=AnalysisListOut)
def list_analyses(
    service: ServiceDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AnalysisListOut:
    rows, total = service.list_analyses(session, limit, offset)
    return AnalysisListOut(items=[_list_item(r) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/{analysis_id}/status", response_model=AnalysisStatusOut, responses=ERRORS)
def get_status(analysis_id: str, service: ServiceDep, session: SessionDep) -> AnalysisStatusOut:
    return AnalysisStatusOut.model_validate(service.get(session, analysis_id))


@router.get("/{analysis_id}", response_model=AnalysisDetailOut, responses=ERRORS)
def get_analysis(analysis_id: str, service: ServiceDep, session: SessionDep) -> AnalysisDetailOut:
    row = service.get(session, analysis_id)
    base = _list_item(row).model_dump()
    return AnalysisDetailOut(
        **base,
        parsed_lines=row.parsed_lines,
        malformed_lines=row.malformed_lines,
        ai_model=row.ai_model,
        prompt_version=row.prompt_version,
        summary_lines=row.summary_lines,
        analysis=row.analysis,
        evidence=row.evidence,
        stats=row.stats,
        redaction_counts=row.redaction_counts,
        timings_ms=row.timings_ms,
        signals=[SignalOut.model_validate(s) for s in service.signals(session, analysis_id)],
        groups=[EventGroupOut.model_validate(g) for g in service.groups(session, analysis_id)],
        services=service.services(session, analysis_id),
    )


@router.get("/{analysis_id}/lines", response_model=LinesPageOut, responses=ERRORS)
def get_lines(
    analysis_id: str,
    service: ServiceDep,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=200, description="Case-insensitive substring search")] = None,
    severity: Annotated[list[str] | None, Query(description="Repeatable: severity=ERROR&severity=WARN")] = None,
    svc: Annotated[str | None, Query(alias="service", max_length=64)] = None,
    malformed_only: bool = False,
    line_numbers: Annotated[str | None, Query(max_length=2000, description="Comma-separated line numbers")] = None,
    around_line: Annotated[int | None, Query(ge=1, description="Return the page that contains this line")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 100,
) -> LinesPageOut:
    numbers: list[int] | None = None
    if line_numbers:
        try:
            numbers = [int(n) for n in line_numbers.split(",") if n.strip()][:500]
        except ValueError as exc:
            raise AppError("VALIDATION_ERROR", "line_numbers must be comma-separated integers", 422) from exc
    result = service.query_lines(
        session,
        analysis_id,
        q=q,
        severities=[s.upper() for s in severity] if severity else None,
        service=svc,
        malformed_only=malformed_only,
        line_numbers=numbers,
        around_line=around_line,
        page=page,
        page_size=page_size,
    )
    return LinesPageOut(
        items=[LogLineOut.model_validate(r) for r in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.get(
    "/{analysis_id}/export", responses={**ERRORS, 200: {"content": {"application/json": {}, "text/markdown": {}}}}
)
def export_analysis(
    analysis_id: str,
    service: ServiceDep,
    session: SessionDep,
    format: Literal["json", "markdown"] = "json",  # noqa: A002 - public query parameter name
) -> Response:
    row = service.get(session, analysis_id)
    if row.status != "completed":
        raise AppError("NOT_READY", "Analysis is not completed yet", 409)
    signals = service.signals(session, analysis_id)
    stem = row.filename.rsplit(".", 1)[0] or "analysis"
    if format == "markdown":
        return Response(
            export_markdown(row, signals),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{stem}-incident.md"'},
        )
    return Response(
        export_json(row, signals),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{stem}-incident.json"'},
    )


@router.delete("/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT, responses=ERRORS)
def delete_analysis(analysis_id: str, service: ServiceDep, session: SessionDep) -> Response:
    service.delete(session, analysis_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
