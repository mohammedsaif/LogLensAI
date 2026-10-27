"""Google Gemini provider using the official google-genai SDK."""

from typing import Any

from google import genai
from google.genai import errors, types

from app.ai.providers.base import ProviderError, ProviderResponse


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str, client: Any | None = None):
        self.model = model
        self._client = client or genai.Client(api_key=api_key)

    async def complete(
        self, *, system: str, user: str, json_schema: dict, max_tokens: int, timeout: float
    ) -> ProviderResponse:
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=json_schema,
            max_output_tokens=max_tokens,
            http_options=types.HttpOptions(timeout=int(timeout * 1000)),  # milliseconds
        )
        try:
            response = await self._client.aio.models.generate_content(model=self.model, contents=user, config=config)
        except errors.APIError as exc:
            code = getattr(exc, "code", None) or 0
            if code in (401, 403):
                raise ProviderError("not_configured", "Gemini API key rejected", retryable=False) from exc
            if code == 429:
                raise ProviderError("rate_limited", "Gemini rate limit reached", retryable=True) from exc
            if code in (408, 504):
                raise ProviderError("timeout", "Gemini request timed out", retryable=True) from exc
            if 400 <= code < 500:
                raise ProviderError("bad_request", f"Gemini rejected the request ({code})", retryable=False) from exc
            raise ProviderError("provider_error", f"Gemini API error {code}", retryable=True) from exc
        except TimeoutError as exc:
            raise ProviderError("timeout", "Gemini request timed out", retryable=True) from exc
        except OSError as exc:
            raise ProviderError("provider_error", "Could not connect to the Gemini API", retryable=True) from exc

        feedback = getattr(response, "prompt_feedback", None)
        if feedback is not None and getattr(feedback, "block_reason", None):
            raise ProviderError("refusal", "Gemini blocked the request", retryable=False)
        candidates = getattr(response, "candidates", None) or []
        finish = str(getattr(candidates[0], "finish_reason", "") or "") if candidates else ""
        if any(word in finish for word in ("SAFETY", "PROHIBITED", "BLOCKLIST", "SPII")):
            raise ProviderError("refusal", "Gemini declined to analyze this evidence", retryable=False)
        if "MAX_TOKENS" in finish:
            raise ProviderError("provider_error", "Gemini response truncated at max tokens", retryable=True)
        text = response.text or ""
        if not text:
            raise ProviderError("provider_error", "Gemini returned an empty response", retryable=True)
        usage = {}
        meta = getattr(response, "usage_metadata", None)
        if meta is not None:
            usage = {
                "input_tokens": getattr(meta, "prompt_token_count", 0) or 0,
                "output_tokens": getattr(meta, "candidates_token_count", 0) or 0,
            }
        return ProviderResponse(text=text, model=self.model, stop_reason=finish or None, usage=usage)
