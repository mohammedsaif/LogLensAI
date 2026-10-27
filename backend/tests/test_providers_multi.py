"""OpenAI(-compatible), Gemini and Ollama providers, tested with fake clients / mocked HTTP (no network, no cost)."""

import json
from types import SimpleNamespace

import httpx
import httpx2
import openai
import pytest
from google.genai import errors as genai_errors

from app.ai.analyzer import analyze
from app.ai.providers.base import ProviderError
from app.ai.providers.factory import get_provider, provider_label, provider_model
from app.ai.providers.gemini_provider import GeminiProvider
from app.ai.providers.mock_provider import MockProvider
from app.ai.providers.ollama_provider import OllamaProvider
from app.ai.providers.openai_provider import OpenAIProvider
from app.ai.schemas import AI_OUTPUT_JSON_SCHEMA
from app.pipeline.orchestrator import run_pipeline
from app.samples.generator import generate_sample
from tests.conftest import make_settings

CALL = dict(system="S", user="U", json_schema=AI_OUTPUT_JSON_SCHEMA, max_tokens=100, timeout=5)


@pytest.fixture(scope="module")
def pack():
    return run_pipeline(generate_sample("pool_exhaustion"), make_settings()).evidence


async def valid_json(pack) -> str:
    """A schema-valid answer for the pack (the mock model's output), so real validation runs end to end."""
    from app.ai.prompts.v1 import build_user_prompt

    return (await MockProvider().complete(**{**CALL, "user": build_user_prompt(pack)})).text


# ---- OpenAI / OpenAI-compatible ------------------------------------------------------------------------------
class FakeCompletions:
    def __init__(self, outcome):
        self.outcome, self.kwargs = outcome, None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def openai_client(outcome):
    completions = FakeCompletions(outcome)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), completions


def chat_response(text="{}", finish="stop", refusal=None):
    return SimpleNamespace(
        model="gpt-test",
        choices=[SimpleNamespace(finish_reason=finish, message=SimpleNamespace(content=text, refusal=refusal))],
        usage=SimpleNamespace(prompt_tokens=900, completion_tokens=200),
    )


def _openai_status(cls, code):
    req = httpx2.Request("POST", "https://api.openai.com/v1/chat/completions")
    return cls("err", response=httpx2.Response(code, request=req), body=None)


async def test_openai_sends_strict_json_schema(pack):
    client, completions = openai_client(chat_response(await valid_json(pack)))
    provider = OpenAIProvider("sk-test", "gpt-test", client=client)
    result = await analyze(pack, provider, make_settings())
    assert result.ai_status == "ok" and result.provider == "openai" and result.model == "gpt-test"
    kw = completions.kwargs
    assert kw["response_format"]["type"] == "json_schema"
    assert kw["response_format"]["json_schema"]["strict"] is True
    assert kw["messages"][0]["role"] == "system" and kw["max_completion_tokens"] == 4000
    assert result.usage == {"input_tokens": 900, "output_tokens": 200}


async def test_openai_compatible_json_object_mode():
    client, completions = openai_client(chat_response())
    provider = OpenAIProvider(
        "", "llama", base_url="http://localhost:1234/v1", response_format="json_object", client=client
    )
    assert provider.name == "openai-compatible"
    await provider.complete(**CALL)
    assert completions.kwargs["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize(
    "exc,kind,retryable",
    [
        (openai.APITimeoutError(request=httpx2.Request("POST", "https://x")), "timeout", True),
        (_openai_status(openai.RateLimitError, 429), "rate_limited", True),
        (_openai_status(openai.AuthenticationError, 401), "not_configured", False),
        (_openai_status(openai.BadRequestError, 400), "bad_request", False),
        (_openai_status(openai.InternalServerError, 503), "provider_error", True),
        (openai.APIConnectionError(request=httpx2.Request("POST", "https://x")), "provider_error", True),
    ],
)
async def test_openai_error_mapping(exc, kind, retryable):
    client, _ = openai_client(exc)
    with pytest.raises(ProviderError) as info:
        await OpenAIProvider("k", "m", client=client).complete(**CALL)
    assert (info.value.kind, info.value.retryable) == (kind, retryable)


@pytest.mark.parametrize(
    "response,kind",
    [
        (chat_response(refusal="I can't help with that"), "refusal"),
        (chat_response(finish="content_filter"), "refusal"),
        (chat_response(finish="length"), "provider_error"),
        (SimpleNamespace(model="m", choices=[], usage=None), "provider_error"),
    ],
)
async def test_openai_finish_reasons(response, kind):
    client, _ = openai_client(response)
    with pytest.raises(ProviderError) as info:
        await OpenAIProvider("k", "m", client=client).complete(**CALL)
    assert info.value.kind == kind


# ---- Gemini --------------------------------------------------------------------------------------------------
class FakeGeminiModels:
    def __init__(self, outcome):
        self.outcome, self.kwargs = outcome, None

    async def generate_content(self, **kwargs):
        self.kwargs = kwargs
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def gemini_client(outcome):
    models = FakeGeminiModels(outcome)
    return SimpleNamespace(aio=SimpleNamespace(models=models)), models


def gemini_response(text="{}", finish="STOP", block=None):
    return SimpleNamespace(
        text=text,
        prompt_feedback=SimpleNamespace(block_reason=block) if block else None,
        candidates=[SimpleNamespace(finish_reason=finish)],
        usage_metadata=SimpleNamespace(prompt_token_count=800, candidates_token_count=150),
    )


async def test_gemini_requests_json_schema_output(pack):
    client, models = gemini_client(gemini_response(await valid_json(pack)))
    result = await analyze(pack, GeminiProvider("g-key", "gemini-test", client=client), make_settings())
    assert result.ai_status == "ok" and result.provider == "gemini"
    config = models.kwargs["config"]
    assert models.kwargs["model"] == "gemini-test"
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == AI_OUTPUT_JSON_SCHEMA
    assert config.system_instruction
    assert config.http_options.timeout == 2_000  # test settings use a 2 s timeout; SDK expects milliseconds


@pytest.mark.parametrize(
    "code,kind,retryable",
    [
        (401, "not_configured", False),
        (403, "not_configured", False),
        (429, "rate_limited", True),
        (400, "bad_request", False),
        (504, "timeout", True),
        (500, "provider_error", True),
    ],
)
async def test_gemini_error_mapping(code, kind, retryable):
    client, _ = gemini_client(genai_errors.APIError(code, {"error": {"message": "x", "status": "X"}}))
    with pytest.raises(ProviderError) as info:
        await GeminiProvider("k", "m", client=client).complete(**CALL)
    assert (info.value.kind, info.value.retryable) == (kind, retryable)


@pytest.mark.parametrize(
    "response,kind",
    [
        (gemini_response(block="SAFETY"), "refusal"),
        (gemini_response(finish="FinishReason.SAFETY"), "refusal"),
        (gemini_response(finish="MAX_TOKENS"), "provider_error"),
        (gemini_response(text=""), "provider_error"),
    ],
)
async def test_gemini_finish_reasons(response, kind):
    client, _ = gemini_client(response)
    with pytest.raises(ProviderError) as info:
        await GeminiProvider("k", "m", client=client).complete(**CALL)
    assert info.value.kind == kind


# ---- Ollama (local) ------------------------------------------------------------------------------------------
def ollama_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_ollama_native_chat_with_schema_and_context_window(pack):
    seen = {}
    answer = await valid_json(pack)

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "llama3.1:8b",
                "message": {"role": "assistant", "content": answer},
                "done_reason": "stop",
                "prompt_eval_count": 1500,
                "eval_count": 300,
            },
        )

    provider = OllamaProvider("llama3.1:8b", "http://ollama:11434/", num_ctx=32768, client=ollama_client(handler))
    result = await analyze(pack, provider, make_settings())
    assert result.ai_status == "ok" and result.provider == "ollama"
    assert seen["url"] == "http://ollama:11434/api/chat"
    body = seen["body"]
    assert body["stream"] is False and body["format"] == AI_OUTPUT_JSON_SCHEMA
    assert body["options"]["num_ctx"] == 32768 and body["options"]["temperature"] == 0
    assert result.usage == {"input_tokens": 1500, "output_tokens": 300}


@pytest.mark.parametrize(
    "status,body,kind,needle",
    [
        (404, {"error": "model 'x' not found"}, "not_configured", "ollama pull"),
        (400, {"error": "invalid format"}, "bad_request", "invalid format"),
        (500, {"error": "out of memory"}, "provider_error", "out of memory"),
    ],
)
async def test_ollama_http_errors(status, body, kind, needle):
    provider = OllamaProvider("x", client=ollama_client(lambda r: httpx.Response(status, json=body)))
    with pytest.raises(ProviderError) as info:
        await provider.complete(**CALL)
    assert info.value.kind == kind and needle in str(info.value)


async def test_ollama_unreachable_and_timeout_and_truncation():
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ProviderError) as info:
        await OllamaProvider("m", client=ollama_client(refuse)).complete(**CALL)
    assert info.value.kind == "not_configured" and "ollama serve" in str(info.value)
    with pytest.raises(ProviderError) as info:
        await OllamaProvider("m", client=ollama_client(slow)).complete(**CALL)
    assert info.value.kind == "timeout" and info.value.retryable
    truncated = lambda r: httpx.Response(200, json={"message": {"content": "{"}, "done_reason": "length"})  # noqa: E731
    with pytest.raises(ProviderError) as info:
        await OllamaProvider("m", client=ollama_client(truncated)).complete(**CALL)
    assert "truncated" in str(info.value)


async def test_ollama_down_gives_actionable_fallback_reason(pack):
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    result = await analyze(pack, OllamaProvider("m", client=ollama_client(refuse)), make_settings())
    assert result.ai_status == "fallback"
    assert "ollama serve" in result.failure_reason
    assert "L120" in " ".join(f.statement for f in result.observed_facts)  # critical signal still preserved


async def test_weak_local_model_invalid_json_falls_back_after_retries(pack):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(
            200, json={"message": {"content": "Sure! Here is the analysis: ..."}, "done_reason": "stop"}
        )

    result = await analyze(pack, OllamaProvider("tiny", client=ollama_client(handler)), make_settings(ai_max_retries=1))
    assert result.ai_status == "fallback" and len(calls) == 2
    assert pack.must_include_ids()[0] in result.critical_evidence_ids


# ---- Factory & config ----------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "overrides,expected_name,needle",
    [
        ({"ai_provider": "openai"}, "openai", "OPENAI_API_KEY"),
        ({"ai_provider": "openai", "openai_api_key": "sk"}, "openai", "OPENAI_MODEL"),
        ({"ai_provider": "gemini"}, "gemini", "GEMINI_API_KEY"),
        ({"ai_provider": "gemini", "gemini_api_key": "g"}, "gemini", "GEMINI_MODEL"),
    ],
)
async def test_factory_reports_missing_configuration(overrides, expected_name, needle, pack):
    settings = make_settings(**overrides)
    provider = get_provider(settings)
    assert provider.name == expected_name
    result = await analyze(pack, provider, settings)
    assert result.ai_status == "fallback" and needle in result.failure_reason


def test_factory_builds_each_provider():
    assert isinstance(
        get_provider(make_settings(ai_provider="openai", openai_api_key="sk", openai_model="m")), OpenAIProvider
    )
    local = get_provider(
        make_settings(ai_provider="openai", openai_base_url="http://localhost:1234/v1", openai_model="m")
    )
    assert isinstance(local, OpenAIProvider) and local.name == "openai-compatible"  # no key needed for local servers
    assert isinstance(
        get_provider(make_settings(ai_provider="gemini", gemini_api_key="g", gemini_model="m")), GeminiProvider
    )
    ollama = get_provider(make_settings(ai_provider="ollama", ollama_model="qwen2.5:7b", ollama_num_ctx=8192))
    assert isinstance(ollama, OllamaProvider) and ollama.model == "qwen2.5:7b" and ollama.num_ctx == 8192


def test_labels_and_models():
    assert provider_label(make_settings(ai_provider="ollama")) == "Local model (Ollama)"
    assert provider_label(make_settings(ai_provider="openai", openai_base_url="http://x/v1")) == "OpenAI-compatible API"
    assert provider_model(make_settings(ai_provider="ollama")) == "llama3.1:8b"
    assert provider_model(make_settings(ai_provider="gemini")) == ""


@pytest.mark.parametrize(
    "overrides,external,label",
    [
        ({"ai_provider": "ollama"}, False, "Local model (Ollama)"),
        ({"ai_provider": "openai", "openai_api_key": "sk-hidden-1", "openai_model": "m"}, True, "OpenAI"),
        (
            {"ai_provider": "openai", "openai_base_url": "http://localhost:1234/v1", "openai_model": "m"},
            False,
            "OpenAI-compatible API",
        ),
        ({"ai_provider": "gemini", "gemini_api_key": "g-hidden-2", "gemini_model": "m"}, True, "Google Gemini"),
        ({"ai_provider": "mock"}, False, "Mock AI (offline, deterministic)"),
    ],
)
def test_config_endpoint_per_provider(client_factory, overrides, external, label):
    body = client_factory(**overrides).get("/api/v1/config").json()
    assert body["ai_external"] is external and body["ai_mode_label"] == label
    assert "hidden" not in json.dumps(body)
