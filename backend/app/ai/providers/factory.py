"""Builds the configured provider. SDKs are imported lazily so unused providers cost nothing."""

from app.ai.providers.base import AIProvider, ProviderError
from app.core.config import Settings

PROVIDER_LABELS = {
    "mock": "Mock AI (offline, deterministic)",
    "anthropic": "Claude (Anthropic)",
    "openai": "OpenAI",
    "gemini": "Google Gemini",
    "ollama": "Local model (Ollama)",
    "disabled": "AI disabled (deterministic only)",
}


def _secret(value) -> str:
    return value.get_secret_value() if value else ""


def provider_model(settings: Settings) -> str:
    """The model name the configured provider will use ("" when it still needs configuring)."""
    return {
        "anthropic": settings.anthropic_model,
        "openai": settings.openai_model or "",
        "gemini": settings.gemini_model or "",
        "ollama": settings.ollama_model,
        "mock": "loglens-mock-1",
    }.get(settings.ai_provider, "none")


def provider_label(settings: Settings) -> str:
    if settings.ai_provider == "openai" and settings.openai_base_url:
        return "OpenAI-compatible API"
    return PROVIDER_LABELS[settings.ai_provider]


def get_provider(settings: Settings) -> AIProvider | None:
    """Returns None when AI is disabled (deterministic summaries only)."""
    match settings.ai_provider:
        case "disabled":
            return None
        case "anthropic":
            key = _secret(settings.anthropic_api_key)
            if not key:
                return _UnconfiguredProvider("anthropic", settings.anthropic_model, "ANTHROPIC_API_KEY is not set")
            from app.ai.providers.anthropic_provider import AnthropicProvider

            return AnthropicProvider(
                api_key=key,
                model=settings.anthropic_model,
                effort=settings.anthropic_effort,
                server_fallbacks=settings.anthropic_server_fallbacks,
            )
        case "openai":
            key = _secret(settings.openai_api_key)
            # Local OpenAI-compatible servers (LM Studio, vLLM, Ollama /v1) usually need no key.
            if not key and not settings.openai_base_url:
                return _UnconfiguredProvider("openai", settings.openai_model or "", "OPENAI_API_KEY is not set")
            if not settings.openai_model:
                return _UnconfiguredProvider("openai", "", "OPENAI_MODEL is not set")
            from app.ai.providers.openai_provider import OpenAIProvider

            return OpenAIProvider(
                api_key=key,
                model=settings.openai_model,
                base_url=settings.openai_base_url,
                response_format=settings.openai_response_format,
            )
        case "gemini":
            key = _secret(settings.gemini_api_key)
            if not key:
                return _UnconfiguredProvider("gemini", settings.gemini_model or "", "GEMINI_API_KEY is not set")
            if not settings.gemini_model:
                return _UnconfiguredProvider("gemini", "", "GEMINI_MODEL is not set")
            from app.ai.providers.gemini_provider import GeminiProvider

            return GeminiProvider(api_key=key, model=settings.gemini_model)
        case "ollama":
            from app.ai.providers.ollama_provider import OllamaProvider

            return OllamaProvider(
                model=settings.ollama_model, base_url=settings.ollama_base_url, num_ctx=settings.ollama_num_ctx
            )
        case _:
            from app.ai.providers.mock_provider import MockProvider

            return MockProvider()


class _UnconfiguredProvider:
    """The selected provider is missing configuration: fail fast so the analyzer uses the deterministic fallback."""

    def __init__(self, name: str, model: str, reason: str):
        self.name = name
        self.model = model
        self.reason = reason

    async def complete(self, **_: object):
        raise ProviderError("not_configured", self.reason, retryable=False)
