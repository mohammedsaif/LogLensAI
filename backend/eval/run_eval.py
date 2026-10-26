"""Evaluation harness: runs every labelled dataset through the full pipeline + analyzer and scores it.

Usage:
  python -m eval.run_eval                      # offline, mock provider (free, deterministic; used in CI)
  python -m eval.run_eval --provider anthropic # live Claude run (requires ANTHROPIC_API_KEY; billed)
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from app.ai.analyzer import analyze
from app.ai.prompts.v1 import SYSTEM_PROMPT, build_user_prompt
from app.ai.providers.base import AIProvider
from app.ai.providers.factory import get_provider
from app.ai.summary import render_summary
from app.core.config import Settings
from app.pipeline.orchestrator import PipelineResult, run_pipeline

ROOT = Path(__file__).parent
DATASETS = ROOT / "datasets"


class RecordingProvider:
    """Wraps a provider to capture the exact prompt sent (to verify redaction / injection handling)."""

    def __init__(self, inner: AIProvider):
        self.inner, self.name, self.model = inner, inner.name, inner.model
        self.prompts: list[str] = []

    async def complete(self, **kwargs: Any):
        self.prompts.append(kwargs["system"] + "\n" + kwargs["user"])
        return await self.inner.complete(**kwargs)


def _group_text(result: PipelineResult, fingerprint: str | None) -> str:
    for g in result.groups:
        if g.fingerprint == fingerprint:
            return g.example_message + " " + g.template
    return ""


async def evaluate_case(case: dict[str, Any], settings: Settings) -> dict[str, Any]:
    text = (DATASETS / case["file"]).read_text(encoding="utf-8")
    result = run_pipeline(text, settings)
    provider = get_provider(settings)
    recorder = RecordingProvider(provider) if provider else None
    analysis = await analyze(result.evidence, recorder, settings)
    summary = render_summary(analysis, result.evidence, result.stats)
    prompt = "\n".join(recorder.prompts) if recorder and recorder.prompts else SYSTEM_PROMPT + build_user_prompt(result.evidence)

    checks: list[dict[str, Any]] = []
    must_items = [i for i in result.evidence.items if i.must_include]
    final_ids = set(analysis.critical_evidence_ids)

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "pass": bool(ok), "detail": detail})

    for target in case["must_find"]:
        line, needle = target.get("line"), target.get("text")
        hits = [
            i
            for i in must_items
            if (line is None or line == i.first_line or line in i.line_refs)
            and (needle is None or needle in _group_text(result, i.group_fingerprint))
        ]
        label = f"L{line}" if line else repr(needle)
        check(f"critical signal preserved in evidence: {label}", bool(hits))
        check(f"critical signal present in final analysis: {label}", any(h.id in final_ids for h in hits))
    for pid in case["expected_patterns"]:
        check(f"pattern detected: {pid}", pid in result.stats["pattern_counts"])
    for exp in case["expected_groups"]:
        match = [g for g in result.groups if exp["contains"] in g.example_message]
        check(
            f"group '{exp['contains']}' count == {exp['count']}",
            any(g.count == exp["count"] for g in match),
            str([g.count for g in match]),
        )
    joined = "\n".join(summary)
    check("summary has exactly 5 lines", len(summary) == 5)
    for mention in case["summary_mentions"]:
        check(f"summary mentions {mention}", mention in joined)
    for key, value in case.get("expected_counts", {}).items():
        check(f"stats.{key} == {value}", result.stats[key] == value, str(result.stats[key]))
    for forbidden in case.get("forbidden_in_prompt", []):
        check(f"not sent to model: {forbidden[:30]}", forbidden not in prompt)
    for word in case.get("title_must_not_contain", []):
        check(f"title avoids '{word}'", word not in analysis.incident_title.lower(), analysis.incident_title)
    check("cause labelled as hypothesis", "hypothesis" in summary[3] and "not confirmed" in summary[3])

    return {
        "file": case["file"],
        "ai_status": analysis.ai_status,
        "failure_reason": analysis.failure_reason,
        "passed": sum(c["pass"] for c in checks),
        "total": len(checks),
        "checks": checks,
        "summary": summary,
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["mock", "anthropic", "disabled"], default="mock")
    args = parser.parse_args()
    settings = Settings(ai_provider=args.provider)
    spec = json.loads((DATASETS / "expected.json").read_text(encoding="utf-8"))
    results = [await evaluate_case(case, settings) for case in spec["cases"]]

    total = sum(r["total"] for r in results)
    passed = sum(r["passed"] for r in results)
    critical = [c for r in results for c in r["checks"] if c["check"].startswith("critical signal")]
    print(f"\nLogLens eval ({spec['version']}, provider={args.provider})")
    for r in results:
        print(f"  {r['file']:<30} {r['passed']:>3}/{r['total']:<3} ai_status={r['ai_status']}")
        for c in r["checks"]:
            if not c["pass"]:
                print(f"      FAIL {c['check']} {c['detail']}")
    print(f"\n  Checks passed: {passed}/{total}")
    print(f"  Critical-signal recall: {sum(c['pass'] for c in critical)}/{len(critical)}")
    out = ROOT / "results" / f"latest-{args.provider}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(
        json.dumps({"provider": args.provider, "passed": passed, "total": total, "results": results}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  Report: {out}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
