import json
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.ai.providers.base import AIProvider, ProviderError, ProviderResponse
from app.ai.providers.mock_provider import MockProvider
from app.core.config import Settings
from app.main import create_app


def make_settings(**overrides) -> Settings:
    base = dict(
        environment="test",
        database_url="sqlite://",
        ai_provider="mock",
        ai_backoff_seconds=0,
        ai_timeout_seconds=2,
        log_json=False,
        log_level="WARNING",
        retention_days=0,
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


class ScriptedProvider:
    """Test double: returns/raises a scripted sequence of outcomes and records prompts."""

    name = "scripted"
    model = "scripted-1"

    def __init__(self, outcomes: list):
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []

    async def complete(self, **kwargs) -> ProviderResponse:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        if callable(outcome):
            return await outcome(**kwargs)
        return ProviderResponse(text=outcome if isinstance(outcome, str) else json.dumps(outcome), model=self.model)


@pytest.fixture
def scripted() -> Callable[[list], ScriptedProvider]:
    return ScriptedProvider


def provider_error(kind="provider_error", retryable=True) -> ProviderError:
    return ProviderError(kind, f"simulated {kind}", retryable)


@pytest.fixture
def client_factory() -> Iterator[Callable[..., TestClient]]:
    clients: list[TestClient] = []

    def _make(provider: AIProvider | None | str = "mock", **overrides) -> TestClient:
        s = make_settings(**overrides)
        if provider == "mock":
            factory = lambda _s: MockProvider()  # noqa: E731
        else:
            factory = lambda _s: provider  # noqa: E731
        client = TestClient(create_app(s, factory))
        client.__enter__()
        clients.append(client)
        return client

    yield _make
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(client_factory) -> TestClient:
    return client_factory()
