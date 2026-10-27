"""OpenAI provider, also used for any OpenAI-compatible server via base_url.

Works with api.openai.com, Azure-hosted / proxy gateways, Groq, Together, OpenRouter, LM Studio, vLLM, and
Ollama's /v1 endpoint. Servers that do not support JSON-schema structured outputs can use
`OPENAI_RESPONSE_FORMAT=json_object`; LogLens validates the JSON with Pydantic either way.
"""

from typing import Any, Literal

import openai

from app.ai.providers.base import ProviderError, ProviderResponse


class OpenAIProvider:
    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        response_format: Literal["json_schema", "json_object"] = "json_schema",
        client: Any | None = None,
    ):
        self.model = model
        self.response_format = response_format
        if base_url:
            self.name = "openai-compatible"
        # LogLens owns the retry policy, so SDK retries are disabled.
        self._client = client or openai.AsyncOpenAI(api_key=api_key or "not-needed", base_url=base_url, max_retries=0)

    async def complete(
        self, *, system: str, user: str, json_schema: dict, max_tokens: int, timeout: float
    ) -> ProviderResponse:
        if self.response_format == "json_schema":
            fmt: dict[str, Any] = {
                "type": "json_schema",
                "json_schema": {"name": "incident_analysis", "schema": json_schema, "strict": True},
            }
        else:
            fmt = {"type": "json_object"}
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                response_format=fmt,
                max_completion_tokens=max_tokens,
                timeout=timeout,
            )
        except openai.APITimeoutError as exc:
            raise ProviderError("timeout", "OpenAI request timed out", retryable=True) from exc
        except openai.RateLimitError as exc:
            raise ProviderError("rate_limited", "OpenAI rate limit reached", retryable=True) from exc
        except (openai.AuthenticationError, openai.PermissionDeniedError) as exc:
            raise ProviderError("not_configured", "OpenAI API key rejected", retryable=False) from exc
        except (openai.BadRequestError, openai.NotFoundError, openai.UnprocessableEntityError) as exc:
            raise ProviderError("bad_request", f"OpenAI rejected the request: {exc.message}", retryable=False) from exc
        except openai.APIStatusError as exc:
            raise ProviderError(
                "provider_error", f"OpenAI API error {exc.status_code}", retryable=exc.status_code >= 500
            ) from exc
        except openai.APIConnectionError as exc:
            raise ProviderError(
                "provider_error", "Could not connect to the OpenAI-compatible API", retryable=True
            ) from exc

        if not response.choices:
            raise ProviderError("provider_error", "OpenAI returned no choices", retryable=True)
        choice = response.choices[0]
        if getattr(choice.message, "refusal", None) or choice.finish_reason == "content_filter":
            raise ProviderError("refusal", "OpenAI declined to analyze this evidence", retryable=False)
        if choice.finish_reason == "length":
            raise ProviderError("provider_error", "OpenAI response truncated at max tokens", retryable=True)
        usage = {}
        if getattr(response, "usage", None) is not None:
            usage = {"input_tokens": response.usage.prompt_tokens, "output_tokens": response.usage.completion_tokens}
        return ProviderResponse(
            text=choice.message.content or "",
            model=response.model or self.model,
            stop_reason=choice.finish_reason,
            usage=usage,
        )
