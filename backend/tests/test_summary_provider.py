"""Five-line summary rendering and the Anthropic provider adapter (with a fake SDK client)."""

from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from app.ai.analyzer import analyze
from app.ai.providers.anthropic_provider import SERVER_FALLBACK_BETA, AnthropicProvider
from app.ai.providers.base import ProviderError
from app.ai.providers.factory import get_provider
from app.ai.providers.mock_provider import MockProvider
from app.ai.summary import SUMMARY_LABELS, render_summary
from app.pipeline.orchestrator import run_pipeline
from app.samples.generator import generate_sample
from tests.conftest import make_settings


@pytest.mark.parametrize("scenario", ["pool_exhaustion", "memory_leak", "auth_attack", "healthy", "prompt_injection"])
async def test_summary_has_exactly_five_labelled_lines(scenario):
    result = run_pipeline(generate_sample(scenario), make_settings())
    analysis = await analyze(result.evidence, MockProvider(), make_settings())
    lines = render_summary(analysis, result.evidence, result.stats)
    assert len(lines) == 5
    for line, label in zip(lines, SUMMARY_LABELS, strict=True):
        assert line.startswith(label)
        assert "\n" not in line and len(line) <= 600
    assert "(hypothesis," in lines[3] and "not confirmed" in lines[3]


async def test_fallback_summary_also_has_five_lines():
    result = run_pipeline(generate_sample("pool_exhaustion"), make_settings())
    analysis = await analyze(result.evidence, None, make_settings())
    lines = render_summary(analysis, result.evidence, result.stats)
    assert len(lines) == 5 and "low confidence" in lines[3]


# ---- Anthropic adapter ------------------------------------------------------------------------------------------
class FakeMessages:
    def __init__(self, outcome):
        self.outcome = outcome
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def fake_client(outcome):
    messages = FakeMessages(outcome)
    return SimpleNamespace(messages=messages, beta=SimpleNamespace(messages=messages)), messages


def message(text='{"a": 1}', stop_reason="end_turn"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
        model="claude-opus-5-5",
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=1200, output_tokens=300),
    )


def _status_error(cls, code):
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("err", response=httpx2.Response(code, request=req), body=None)


async def test_anthropic_provider_sends_structured_output_request_with_fallbacks():
    client, messages = fake_client(message())
    provider = AnthropicProvider("k", "claude-opus-5-5", effort="medium", client=client)
    resp = await provider.complete(system="S", user="U", json_schema={"type": "object"}, max_tokens=100, timeout=5)
    assert resp.text == '{"a": 1}' and resp.usage == {"input_tokens": 1200, "output_tokens": 300}
    kw = messages.kwargs
    assert kw["model"] == "claude-opus-5-5" and kw["system"] == "S"
    assert kw["output_config"]["format"]["type"] == "json_schema"
    assert kw["output_config"]["effort"] == "medium"
    assert kw["betas"] == [SERVER_FALLBACK_BETA] and kw["fallbacks"] == "default"
    assert kw["timeout"] == 5


async def test_anthropic_provider_without_server_fallbacks_uses_plain_create():
    client, messages = fake_client(message())
    provider = AnthropicProvider("k", "claude-opus-5-5", server_fallbacks=False, client=client)
    await provider.complete(system="S", user="U", json_schema={}, max_tokens=10, timeout=1)
    assert "betas" not in messages.kwargs


@pytest.mark.parametrize(
    "exc,kind,retryable",
    [
        (anthropic.APITimeoutError(request=httpx2.Request("POST", "https://x")), "timeout", True),
        (_status_error(anthropic.RateLimitError, 429), "rate_limited", True),
        (_status_error(anthropic.AuthenticationError, 401), "not_configured", False),
        (_status_error(anthropic.BadRequestError, 400), "bad_request", False),
        (_status_error(anthropic.InternalServerError, 500), "provider_error", True),
        (anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x")), "provider_error", True),
    ],
)
async def test_anthropic_errors_map_to_provider_errors(exc, kind, retryable):
    client, _ = fake_client(exc)
    provider = AnthropicProvider("k", "m", client=client)
    with pytest.raises(ProviderError) as info:
        await provider.complete(system="S", user="U", json_schema={}, max_tokens=10, timeout=1)
    assert info.value.kind == kind and info.value.retryable is retryable


@pytest.mark.parametrize("stop_reason,kind", [("refusal", "refusal"), ("max_tokens", "provider_error")])
async def test_anthropic_stop_reasons(stop_reason, kind):
    client, _ = fake_client(message(stop_reason=stop_reason))
    with pytest.raises(ProviderError) as info:
        await AnthropicProvider("k", "m", client=client).complete(system="S", user="U", json_schema={}, max_tokens=10, timeout=1)
    assert info.value.kind == kind


async def test_factory_without_key_yields_not_configured_fallback():
    settings = make_settings(ai_provider="anthropic", anthropic_api_key=None)
    provider = get_provider(settings)
    result = run_pipeline(generate_sample("pool_exhaustion", 200), settings)
    analysis = await analyze(result.evidence, provider, settings)
    assert analysis.ai_status == "fallback" and "not configured" in analysis.failure_reason


def test_factory_modes():
    assert get_provider(make_settings(ai_provider="disabled")) is None
    assert get_provider(make_settings(ai_provider="mock")).name == "mock"
    assert isinstance(get_provider(make_settings(ai_provider="anthropic", anthropic_api_key="sk-test")), AnthropicProvider)
