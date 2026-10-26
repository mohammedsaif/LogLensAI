"""Schema for the model's structured output, plus the final stored incident analysis."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Confidence = Literal["low", "medium", "high"]
Priority = Literal["immediate", "short_term", "long_term"]
AIStatus = Literal["ok", "fallback", "disabled"]


class ObservedFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statement: str = Field(min_length=3, max_length=500)
    evidence_ids: list[str] = Field(min_length=1, max_length=10)


class Hypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statement: str = Field(min_length=3, max_length=500)
    confidence: Confidence
    rationale: str = Field(default="", max_length=600)
    evidence_ids: list[str] = Field(min_length=1, max_length=10)


class Recommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(min_length=3, max_length=400)
    priority: Priority
    evidence_ids: list[str] = Field(default_factory=list, max_length=10)


class AIAnalysis(BaseModel):
    """Exactly what the model must return (validated with Pydantic after parsing)."""

    model_config = ConfigDict(extra="forbid")
    incident_title: str = Field(min_length=3, max_length=160)
    impact: str = Field(min_length=3, max_length=500)
    observed_facts: list[ObservedFact] = Field(min_length=1, max_length=10)
    hypotheses: list[Hypothesis] = Field(default_factory=list, max_length=5)
    recommendations: list[Recommendation] = Field(min_length=1, max_length=6)
    critical_evidence_ids: list[str] = Field(default_factory=list, max_length=40)
    overall_confidence: Confidence
    uncertainty_notes: list[str] = Field(default_factory=list, max_length=6)


class IncidentAnalysis(AIAnalysis):
    """Validated analysis enriched with deterministic guarantees and provenance (stored and returned by the API)."""

    model_config = ConfigDict(extra="forbid")
    ai_status: AIStatus
    failure_reason: str | None = None
    provider: str
    model: str
    prompt_version: str
    attempts: int = 0
    reattached_evidence_ids: list[str] = Field(default_factory=list)
    validation_warnings: list[str] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)


def _string_array() -> dict:
    return {"type": "array", "items": {"type": "string"}}


# JSON Schema sent to the provider (Claude structured outputs). Length limits are enforced by Pydantic afterwards.
AI_OUTPUT_JSON_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "incident_title",
        "impact",
        "observed_facts",
        "hypotheses",
        "recommendations",
        "critical_evidence_ids",
        "overall_confidence",
        "uncertainty_notes",
    ],
    "properties": {
        "incident_title": {"type": "string"},
        "impact": {"type": "string"},
        "observed_facts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["statement", "evidence_ids"],
                "properties": {"statement": {"type": "string"}, "evidence_ids": _string_array()},
            },
        },
        "hypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["statement", "confidence", "rationale", "evidence_ids"],
                "properties": {
                    "statement": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                    "rationale": {"type": "string"},
                    "evidence_ids": _string_array(),
                },
            },
        },
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["action", "priority", "evidence_ids"],
                "properties": {
                    "action": {"type": "string"},
                    "priority": {"type": "string", "enum": ["immediate", "short_term", "long_term"]},
                    "evidence_ids": _string_array(),
                },
            },
        },
        "critical_evidence_ids": _string_array(),
        "overall_confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "uncertainty_notes": _string_array(),
    },
}
