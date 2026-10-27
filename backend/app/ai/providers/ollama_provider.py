"""Local models through Ollama's native /api/chat endpoint. Logs never leave the machine/network.

Uses Ollama structured outputs (`format` = JSON schema). `num_ctx` is set explicitly because Ollama's default
context window is small and would silently truncate the evidence pack.
"""

from typing import Any

import httpx

from app.ai.providers.base import ProviderError, ProviderResponse


class OllamaProvider:
    name = "ollama"

    def __init__(
        self, model: str, base_url: str = "http://localhost:11434", num_ctx: int = 16384, client: Any | None = None
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.num_ctx = num_ctx
        self._client = client

    async def complete(
        self, *, system: str, user: str, json_schema: dict, max_tokens: int, timeout: float
    ) -> ProviderResponse:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "format": json_schema,
            "options": {"num_ctx": self.num_ctx, "num_predict": max_tokens, "temperature": 0},
        }
        try:
            if self._client is not None:
                response = await self._client.post(f"{self.base_url}/api/chat", json=payload, timeout=timeout)
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(f"{self.base_url}/api/chat", json=payload, timeout=timeout)
        except httpx.TimeoutException as exc:
            raise ProviderError("timeout", "Local model (Ollama) timed out", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                "not_configured", f"Cannot reach Ollama at {self.base_url}. Is `ollama serve` running?", retryable=False
            ) from exc

        if response.status_code == 404:
            raise ProviderError(
                "not_configured",
                f"Model '{self.model}' is not available. Run: ollama pull {self.model}",
                retryable=False,
            )
        if response.status_code >= 400:
            detail = ""
            try:
                detail = str(response.json().get("error", ""))[:200]
            except ValueError:
                pass
            kind = "bad_request" if response.status_code < 500 else "provider_error"
            raise ProviderError(
                kind, f"Ollama error {response.status_code}: {detail}", retryable=response.status_code >= 500
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError("provider_error", "Ollama returned a non-JSON body", retryable=True) from exc
        if data.get("done_reason") == "length":
            raise ProviderError(
                "provider_error", "Local model output truncated (raise AI_MAX_OUTPUT_TOKENS)", retryable=True
            )
        text = (data.get("message") or {}).get("content", "")
        usage = {
            "input_tokens": int(data.get("prompt_eval_count") or 0),
            "output_tokens": int(data.get("eval_count") or 0),
        }
        return ProviderResponse(
            text=text, model=data.get("model") or self.model, stop_reason=data.get("done_reason"), usage=usage
        )
