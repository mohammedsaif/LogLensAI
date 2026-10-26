"""Provider abstraction: any model backend implements AIProvider."""

from dataclasses import dataclass, field
from typing import Literal, Protocol

ErrorKind = Literal["timeout", "rate_limited", "provider_error", "refusal", "not_configured", "bad_request"]


@dataclass
class ProviderResponse:
    text: str
    model: str
    stop_reason: str | None = None
    usage: dict[str, int] = field(default_factory=dict)


class ProviderError(Exception):
    def __init__(self, kind: ErrorKind, message: str, retryable: bool):
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable


class AIProvider(Protocol):
    name: str
    model: str

    async def complete(
        self, *, system: str, user: str, json_schema: dict, max_tokens: int, timeout: float
    ) -> ProviderResponse: ...
