"""Runs the deterministic pipeline stages in order."""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.config import Settings
from app.pipeline.aggregator import aggregate, enrich_records
from app.pipeline.evidence import EvidencePack, build_evidence_pack
from app.pipeline.models import EventGroup, LogRecord, Signal
from app.pipeline.parser import parse_text
from app.pipeline.signals import detect_signals
from app.pipeline.stats import compute_stats

ProgressCallback = Callable[[str, int], None]


@dataclass
class PipelineResult:
    records: list[LogRecord]
    groups: list[EventGroup]
    signals: list[Signal]
    stats: dict[str, Any]
    evidence: EvidencePack
    timings_ms: dict[str, float] = field(default_factory=dict)


def run_pipeline(text: str, settings: Settings, progress: ProgressCallback | None = None) -> PipelineResult:
    report = progress or (lambda stage, pct: None)
    timings: dict[str, float] = {}

    def timed(name: str, start: float) -> None:
        timings[name] = round((time.perf_counter() - start) * 1000, 2)

    t = time.perf_counter()
    report("parsing", 15)
    records = parse_text(text)
    timed("parse", t)

    t = time.perf_counter()
    report("aggregating", 35)
    enrich_records(records)
    groups = aggregate(records)
    timed("aggregate", t)

    t = time.perf_counter()
    report("detecting_signals", 50)
    signals = detect_signals(groups, settings)
    stats = compute_stats(records, groups)
    timed("signals_stats", t)

    t = time.perf_counter()
    report("selecting_evidence", 60)
    evidence = build_evidence_pack(
        groups,
        signals,
        stats,
        token_budget=settings.evidence_token_budget,
        max_items=settings.evidence_max_items,
        redact_ips=settings.redact_ip_addresses,
    )
    timed("evidence", t)
    return PipelineResult(records, groups, signals, stats, evidence, timings)
