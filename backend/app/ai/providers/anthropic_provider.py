"""Claude provider using the official Anthropic Python SDK."""

from typing import Any

import anthropic

from app.ai.providers.base import ProviderError, ProviderResponse

SERVER_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        model: str,
        effort: str = "medium",
        server_fallbacks: bool = True,
        client: Any | None = None,
    ):
        self.model = model
        self.effort = effort
        self.server_fallbacks = server_fallbacks
        # LogLens owns the retry policy (bounded attempts + fallback), so SDK retries are disabled.
        self._client = client or anthropic.AsyncAnthropic(api_key=api_key, max_retries=0)

    async def complete(
        self, *, system: str, user: str, json_schema: dict, max_tokens: int, timeout: float
    ) -> ProviderResponse:
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": {"effort": self.effort, "format": {"type": "json_schema", "schema": json_schema}},
            "timeout": timeout,
        }
        try:
            if self.server_fallbacks:
                # On a safety-classifier decline the API re-runs the request on a fallback model in the same call.
                response = await self._client.beta.messages.create(
                    **params, betas=[SERVER_FALLBACK_BETA], fallbacks="default"
                )
            else:
                response = await self._client.messages.create(**params)
        except anthropic.APITimeoutError as exc:
            raise ProviderError("timeout", "Claude request timed out", retryable=True) from exc
        except anthropic.RateLimitError as exc:
            raise ProviderError("rate_limited", "Claude rate limit reached", retryable=True) from exc
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            raise ProviderError("not_configured", "Claude API key rejected", retryable=False) from exc
        except (anthropic.BadRequestError, anthropic.NotFoundError, anthropic.UnprocessableEntityError) as exc:
            raise ProviderError("bad_request", f"Claude rejected the request: {exc.message}", retryable=False) from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(
                "provider_error", f"Claude API error {exc.status_code}", retryable=exc.status_code >= 500
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError("provider_error", "Could not connect to the Claude API", retryable=True) from exc

        if response.stop_reason == "refusal":
            raise ProviderError("refusal", "Claude declined to analyze this evidence", retryable=False)
        if response.stop_reason == "max_tokens":
            raise ProviderError("provider_error", "Claude response truncated at max_tokens", retryable=True)
        text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        usage = {}
        if getattr(response, "usage", None) is not None:
            usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
        return ProviderResponse(text=text, model=response.model, stop_reason=response.stop_reason, usage=usage)
