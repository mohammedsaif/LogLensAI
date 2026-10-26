"""FastAPI dependencies resolved from application state."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.incident_service import IncidentService


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_service(request: Request) -> IncidentService:
    return request.app.state.incidents


def get_db_session(request: Request) -> Iterator[Session]:
    with request.app.state.db.session() as session:
        yield session
