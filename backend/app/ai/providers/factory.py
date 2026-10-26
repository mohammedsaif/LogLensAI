"""Builds the configured provider."""

from app.ai.providers.base import AIProvider
from app.core.config import Settings


def get_provider(settings: Settings) -> AIProvider | None:
    """Returns None when AI is disabled (deterministic summaries only)."""
    if settings.ai_provider == "disabled":
        return None
    if settings.ai_provider == "anthropic":
        from app.ai.providers.anthropic_provider import AnthropicProvider

        key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else ""
        if not key:
            return _UnconfiguredProvider(settings.anthropic_model)
        return AnthropicProvider(
            api_key=key,
            model=settings.anthropic_model,
            effort=settings.anthropic_effort,
            server_fallbacks=settings.anthropic_server_fallbacks,
        )
    from app.ai.providers.mock_provider import MockProvider

    return MockProvider()


class _UnconfiguredProvider:
    """Selected provider is anthropic but no key is set: fail fast so the analyzer uses the fallback."""

    name = "anthropic"

    def __init__(self, model: str):
        self.model = model

    async def complete(self, **_: object):
        from app.ai.providers.base import ProviderError

        raise ProviderError("not_configured", "ANTHROPIC_API_KEY is not set", retryable=False)
