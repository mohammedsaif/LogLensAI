"""API integration tests (FastAPI TestClient + in-memory SQLite + mocked AI)."""

import json

import pytest

from app.samples.generator import generate_sample
from tests.conftest import provider_error


def upload(client, content: bytes | str, name: str = "app.log"):
    data = content.encode() if isinstance(content, str) else content
    return client.post("/api/v1/analyses", files={"file": (name, data, "text/plain")})


def completed(client, content=None, name="app.log") -> dict:
    resp = upload(client, content or generate_sample("pool_exhaustion"), name)
    assert resp.status_code == 202, resp.text
    analysis_id = resp.json()["id"]
    detail = client.get(f"/api/v1/analyses/{analysis_id}").json()
    assert detail["status"] == "completed", detail
    return detail


def test_health_endpoints(client):
    assert client.get("/health/live").json()["status"] == "ok"
    ready = client.get("/health/ready")
    assert ready.status_code == 200 and ready.json()["database"] == "up"
    assert "X-Request-ID" in ready.headers


def test_config_exposes_no_secrets(client_factory):
    client = client_factory(ai_provider="anthropic", anthropic_api_key="sk-ant-secret-value-123")
    body = client.get("/api/v1/config").json()
    assert body["ai_provider"] == "anthropic" and body["ai_model"] == "claude-opus-5-5"
    assert "sk-ant-secret-value-123" not in json.dumps(body)
    assert {s["id"] for s in body["scenarios"]} >= {"pool_exhaustion", "healthy"}


def test_upload_returns_202_and_completes(client):
    resp = upload(client, generate_sample("pool_exhaustion"))
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued" and body["filename"] == "app.log"
    status = client.get(f"/api/v1/analyses/{body['id']}/status").json()
    assert status["status"] == "completed" and status["progress"] == 100


def test_detail_contains_summary_signals_groups_and_stats(client):
    d = completed(client)
    assert len(d["summary_lines"]) == 5
    assert d["errors"] == 161 and d["warnings"] == 16 and d["critical"] == 0
    assert d["ai_status"] == "ok" and d["ai_provider"] == "mock"
    assert d["prompt_version"].startswith("incident-analysis/")
    assert d["signals"][0]["line_no"] == 120 and d["signals"][0]["must_include"]
    assert any(g["count"] == 143 for g in d["groups"])
    assert d["stats"]["timeline"] and d["services"]
    assert d["analysis"]["observed_facts"] and d["evidence"]["items"]


@pytest.mark.parametrize(
    "content,name,status,code",
    [
        (b"", "a.log", 400, "EMPTY_FILE"),
        (b"   \n\n  ", "a.log", 400, "NO_LOG_CONTENT"),
        (b"hello", "a.exe", 415, "UNSUPPORTED_FILE_TYPE"),
        (b"hello", "noext", 415, "UNSUPPORTED_FILE_TYPE"),
        (b"\x00\x01\x02binary", "a.log", 400, "BINARY_CONTENT"),
        (b"caf\xe9 latin-1", "a.txt", 400, "INVALID_ENCODING"),
    ],
)
def test_invalid_uploads_are_rejected_with_error_envelope(client, content, name, status, code):
    resp = upload(client, content, name)
    assert resp.status_code == status
    err = resp.json()["error"]
    assert err["code"] == code and err["message"] and "request_id" in err


def test_oversized_upload_is_rejected(client_factory):
    client = client_factory(max_upload_mb=0.001)  # ~1 KB
    resp = upload(client, "x INFO y\n" * 500)
    assert resp.status_code == 413 and resp.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_too_many_lines_rejected(client_factory):
    client = client_factory(max_lines=10)
    resp = upload(client, "a INFO b\n" * 11)
    assert resp.status_code == 413 and resp.json()["error"]["code"] == "TOO_MANY_LINES"


def test_missing_file_field_is_validation_error(client):
    resp = client.post("/api/v1/analyses")
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_bom_and_malformed_lines_are_handled(client):
    content = "﻿2026-01-01T00:00:00Z ERROR [api] boom\nnot a log line\n{bad json\n".encode()
    d = completed(client, content)
    assert d["malformed_lines"] == 2 and d["errors"] == 1


def test_jsonl_upload(client):
    d = completed(client, generate_sample("pool_exhaustion", fmt="jsonl"), "app.jsonl")
    assert d["errors"] == 161 and d["signals"][0]["line_no"] == 120


def test_lines_search_filters_and_pagination(client):
    d = completed(client)
    base = f"/api/v1/analyses/{d['id']}/lines"
    page = client.get(base, params={"page_size": 50}).json()
    assert page["total"] == 1000 and len(page["items"]) == 50 and page["items"][0]["line_no"] == 1

    errors = client.get(base, params={"severity": "ERROR", "page_size": 500}).json()
    assert errors["total"] == 161 and {i["severity"] for i in errors["items"]} == {"ERROR"}

    multi = client.get(base, params=[("severity", "ERROR"), ("severity", "warn")]).json()
    assert multi["total"] == 177

    search = client.get(base, params={"q": "pool usage"}).json()
    assert search["total"] == 1 and search["items"][0]["line_no"] == 120
    assert search["items"][0]["raw"].endswith("Connection pool usage reached 95%")

    svc = client.get(base, params={"service": "api-gateway", "severity": "ERROR"}).json()
    assert svc["total"] == 18

    around = client.get(base, params={"around_line": 120, "page_size": 50}).json()
    assert around["page"] == 3 and any(i["line_no"] == 120 for i in around["items"])

    picked = client.get(base, params={"line_numbers": "120,1,999"}).json()
    assert [i["line_no"] for i in picked["items"]] == [1, 120, 999]


def test_search_treats_wildcards_literally(client):
    d = completed(client, "2026-01-01T00:00:00Z INFO [a] 100% done\n2026-01-01T00:00:01Z INFO [a] almost\n")
    res = client.get(f"/api/v1/analyses/{d['id']}/lines", params={"q": "%"}).json()
    assert res["total"] == 1


def test_lines_bad_line_numbers_param(client):
    d = completed(client)
    resp = client.get(f"/api/v1/analyses/{d['id']}/lines", params={"line_numbers": "1,abc"})
    assert resp.status_code == 422


def test_export_json_and_markdown(client):
    d = completed(client)
    j = client.get(f"/api/v1/analyses/{d['id']}/export", params={"format": "json"})
    assert j.status_code == 200 and "attachment" in j.headers["content-disposition"]
    data = j.json()
    assert len(data["summary_lines"]) == 5 and data["critical_signals"][0]["line_no"] == 120
    md = client.get(f"/api/v1/analyses/{d['id']}/export", params={"format": "markdown"})
    assert md.status_code == 200 and md.headers["content-type"].startswith("text/markdown")
    text = md.text
    assert "## Five-line summary" in text and "| L120 |" in text and "Hypotheses (not confirmed)" in text


def test_history_list_and_delete(client):
    a = completed(client)
    b = completed(client, generate_sample("healthy", 200))
    listing = client.get("/api/v1/analyses", params={"limit": 10}).json()
    assert listing["total"] == 2
    assert {i["id"] for i in listing["items"]} == {a["id"], b["id"]}
    assert all("incident_title" in i for i in listing["items"])
    assert client.delete(f"/api/v1/analyses/{a['id']}").status_code == 204
    assert client.get(f"/api/v1/analyses/{a['id']}").status_code == 404
    assert client.get(f"/api/v1/analyses/{a['id']}/lines").status_code == 404
    assert client.delete(f"/api/v1/analyses/{a['id']}").status_code == 404


def test_unknown_analysis_returns_404_envelope(client):
    resp = client.get("/api/v1/analyses/doesnotexist")
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "NOT_FOUND"


def test_sample_analyze_and_download(client):
    resp = client.post("/api/v1/samples/analyze", json={"scenario": "memory_leak", "lines": 500})
    assert resp.status_code == 202
    d = client.get(f"/api/v1/analyses/{resp.json()['id']}").json()
    assert d["status"] == "completed" and d["source"] == "sample" and d["critical"] == 1
    dl = client.get("/api/v1/samples/download", params={"scenario": "pool_exhaustion"})
    assert dl.status_code == 200 and dl.text.splitlines()[119].endswith("Connection pool usage reached 95%")
    assert client.post("/api/v1/samples/analyze", json={"scenario": "nope"}).status_code == 422
    assert client.post("/api/v1/samples/analyze", json={"lines": 10}).status_code == 422


def test_ai_provider_failure_still_completes_with_fallback(client_factory, scripted):
    client = client_factory(scripted([provider_error("provider_error", True)]))
    d = completed(client)
    assert d["ai_status"] == "fallback" and d["confidence"] == "low"
    assert d["analysis"]["failure_reason"] == "AI provider error"
    assert len(d["summary_lines"]) == 5 and "L120" in d["summary_lines"][2]


def test_ai_disabled_mode(client_factory):
    client = client_factory(None)
    d = completed(client)
    assert d["ai_status"] == "disabled"


def test_pipeline_crash_marks_analysis_failed(client, monkeypatch):
    import app.services.incident_service as svc

    def boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(svc, "run_pipeline", boom)
    resp = upload(client, "2026-01-01T00:00:00Z ERROR [a] b\n")
    status = client.get(f"/api/v1/analyses/{resp.json()['id']}/status").json()
    assert status["status"] == "failed" and status["error_code"] == "PIPELINE_ERROR"
    assert "kaboom" not in status["error_message"]  # internals are not leaked
    export = client.get(f"/api/v1/analyses/{resp.json()['id']}/export")
    assert export.status_code == 409


def test_interrupted_jobs_are_marked_on_startup(client_factory):
    from app.main import create_app
    from tests.conftest import make_settings

    client = client_factory()
    service = client.app.state.incidents
    row = service.create("x.log", 1, "upload", 1)
    assert service.mark_interrupted() == 1
    with service.db.session() as s:
        assert service.get(s, row.id).error_code == "INTERRUPTED"
    assert create_app(make_settings())  # factory is re-entrant


def test_retention_purge(client_factory):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from app.db.models import Analysis

    client = client_factory(retention_days=7)
    service = client.app.state.incidents
    d = completed(client, "2026-01-01T00:00:00Z ERROR [a] b\n")
    with service.db.session() as s:
        s.execute(update(Analysis).values(created_at=datetime.now(UTC) - timedelta(days=30)))
        s.commit()
    assert service.purge_expired() == 1
    assert client.get(f"/api/v1/analyses/{d['id']}").status_code == 404


def test_openapi_docs_available(client):
    spec = client.get("/openapi.json").json()
    assert "/api/v1/analyses" in spec["paths"] and "/api/v1/analyses/{analysis_id}/lines" in spec["paths"]


def test_datetimes_are_serialized_as_utc(client):
    d = completed(client)
    assert d["created_at"].endswith(("Z", "+00:00"))
    line = client.get(f"/api/v1/analyses/{d['id']}/lines", params={"line_numbers": "120"}).json()["items"][0]
    assert line["ts"].startswith("2026-03-14T09:02:29.232") and line["ts"].endswith(("Z", "+00:00"))
    assert d["signals"][0]["ts"].endswith(("Z", "+00:00"))
