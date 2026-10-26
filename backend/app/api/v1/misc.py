"""Config and synthetic sample endpoints."""

from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, status

from app import __version__
from app.ai.prompts.v1 import PROMPT_VERSION
from app.api.deps import get_service, get_settings_dep
from app.core.config import Settings
from app.samples.generator import SCENARIOS, generate_sample
from app.schemas.api import AnalysisStatusOut, ConfigOut, SampleRequest, ScenarioOut
from app.services.incident_service import IncidentService

router = APIRouter(tags=["config & samples"])

_MODE_LABELS = {
    "mock": "Mock AI (offline, deterministic)",
    "anthropic": "Claude",
    "disabled": "AI disabled (deterministic only)",
}


@router.get("/config", response_model=ConfigOut)
def get_config(settings: Annotated[Settings, Depends(get_settings_dep)]) -> ConfigOut:
    """Public runtime configuration. Never includes secrets."""
    return ConfigOut(
        app_name=settings.app_name,
        version=__version__,
        environment=settings.environment,
        ai_provider=settings.ai_provider,
        ai_model={"anthropic": settings.anthropic_model, "mock": "loglens-mock-1"}.get(settings.ai_provider, "none"),
        ai_mode_label=_MODE_LABELS[settings.ai_provider],
        prompt_version=PROMPT_VERSION,
        ai_timeout_seconds=settings.ai_timeout_seconds,
        ai_max_retries=settings.ai_max_retries,
        evidence_token_budget=settings.evidence_token_budget,
        max_upload_mb=settings.max_upload_mb,
        max_lines=settings.max_lines,
        allowed_extensions=settings.allowed_extensions,
        retention_days=settings.retention_days,
        redaction_enabled=True,
        redact_ip_addresses=settings.redact_ip_addresses,
        scenarios=[ScenarioOut(id=k, description=v) for k, v in SCENARIOS.items()],
    )


@router.post("/samples/analyze", status_code=status.HTTP_202_ACCEPTED, response_model=AnalysisStatusOut)
async def analyze_sample(
    body: SampleRequest,
    background: BackgroundTasks,
    service: Annotated[IncidentService, Depends(get_service)],
) -> AnalysisStatusOut:
    """Generate a synthetic log (fictional data) and analyze it."""
    text = generate_sample(body.scenario, body.lines, body.format, body.seed)
    ext = "jsonl" if body.format == "jsonl" else "log"
    row = service.create(f"sample-{body.scenario}-{body.lines}.{ext}", len(text.encode()), "sample", body.lines)
    background.add_task(service.process, row.id, text)
    return AnalysisStatusOut.model_validate(row)


@router.get("/samples/download")
def download_sample(
    scenario: Literal[
        "pool_exhaustion", "auth_attack", "memory_leak", "healthy", "prompt_injection"
    ] = "pool_exhaustion",
    lines: Annotated[int, Query(ge=50, le=50_000)] = 1000,
    format: Literal["text", "jsonl"] = "text",  # noqa: A002
    seed: Annotated[int, Query(ge=0)] = 42,
) -> Response:
    text = generate_sample(scenario, lines, format, seed)
    ext = "jsonl" if format == "jsonl" else "log"
    return Response(
        text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="sample-{scenario}-{lines}.{ext}"'},
    )
