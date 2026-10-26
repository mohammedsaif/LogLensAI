"""Offline, deterministic mock model. Clearly labelled in the UI as "Mock AI".

It reads the evidence JSON from the prompt (exactly what Claude would see) and answers with schema-valid JSON
built by transparent rules, so the full parse -> validate -> render path runs without a paid API key.
"""

import json

from app.ai.heuristics import build_heuristic_analysis
from app.ai.prompts.v1 import EVIDENCE_CLOSE, EVIDENCE_OPEN
from app.ai.providers.base import ProviderError, ProviderResponse
from app.pipeline.evidence import EvidenceItem, EvidencePack


class MockProvider:
    name = "mock"
    model = "loglens-mock-1"

    async def complete(
        self, *, system: str, user: str, json_schema: dict, max_tokens: int, timeout: float
    ) -> ProviderResponse:
        try:
            start = user.index(EVIDENCE_OPEN) + len(EVIDENCE_OPEN)
            end = user.rindex(EVIDENCE_CLOSE)
            payload = json.loads(user[start:end])
        except (ValueError, json.JSONDecodeError) as exc:
            raise ProviderError(
                "bad_request", "Mock provider could not read the evidence block", retryable=False
            ) from exc
        items = [
            EvidenceItem(source="signal" if raw.get("kind") else "group", risk_score=0, **raw)
            for raw in payload.get("items", [])
        ]
        # Restore ordering signal used by the heuristics (higher in the list = higher risk).
        for rank, item in enumerate(items):
            item.risk_score = len(items) - rank
        pack = EvidencePack(
            items=items, stats=payload.get("stats", {}), omitted_group_count=payload.get("omitted_group_count", 0)
        )
        analysis = build_heuristic_analysis(pack, mode="mock")
        text = analysis.model_dump_json()
        return ProviderResponse(
            text=text,
            model=self.model,
            stop_reason="end_turn",
            usage={"input_tokens": len(user) // 4, "output_tokens": len(text) // 4},
        )
