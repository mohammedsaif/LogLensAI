"""Performance budgets (1k and 50k lines) and the offline evaluation dataset."""

import asyncio
import time

import pytest

from app.pipeline.orchestrator import run_pipeline
from app.samples.generator import generate_sample
from eval.run_eval import DATASETS, evaluate_case
from tests.conftest import make_settings


@pytest.mark.performance
def test_pipeline_1000_lines_under_one_second():
    text = generate_sample("pool_exhaustion", 1000)
    start = time.perf_counter()
    result = run_pipeline(text, make_settings())
    elapsed = time.perf_counter() - start
    assert result.stats["total_lines"] == 1000
    assert elapsed < 1.0, f"1k lines took {elapsed:.2f}s"


@pytest.mark.performance
def test_pipeline_50000_lines_under_fifteen_seconds():
    text = generate_sample("pool_exhaustion", 50_000)
    start = time.perf_counter()
    result = run_pipeline(text, make_settings())
    elapsed = time.perf_counter() - start
    assert result.stats["total_lines"] == 50_000
    assert any(s.must_include and s.kind == "precursor" for s in result.signals)
    assert elapsed < 15.0, f"50k lines took {elapsed:.2f}s"


@pytest.mark.performance
def test_api_end_to_end_1000_lines_under_five_seconds(client):
    start = time.perf_counter()
    resp = client.post("/api/v1/samples/analyze", json={"scenario": "pool_exhaustion", "lines": 1000})
    detail = client.get(f"/api/v1/analyses/{resp.json()['id']}").json()
    elapsed = time.perf_counter() - start
    assert detail["status"] == "completed"
    assert elapsed < 5.0, f"API end-to-end took {elapsed:.2f}s"


@pytest.mark.performance
def test_api_upload_20000_lines(client):
    text = generate_sample("memory_leak", 20_000)
    start = time.perf_counter()
    resp = client.post("/api/v1/analyses", files={"file": ("big.log", text.encode(), "text/plain")})
    detail = client.get(f"/api/v1/analyses/{resp.json()['id']}").json()
    elapsed = time.perf_counter() - start
    assert detail["status"] == "completed" and detail["total_lines"] == 20_000
    assert elapsed < 20.0, f"20k-line upload took {elapsed:.2f}s"


def _cases():
    import json

    return json.loads((DATASETS / "expected.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["file"])
def test_evaluation_dataset_expected_findings(case):
    report = asyncio.run(evaluate_case(case, make_settings()))
    failed = [c for c in report["checks"] if not c["pass"]]
    assert not failed, failed
