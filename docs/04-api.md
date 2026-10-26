# LogLens AI — API Reference (v1)

- Base path: `/api/v1`. Interactive documentation is served by FastAPI at `/docs` (Swagger UI) and `/redoc`. The machine-readable schema is at `/openapi.json`.
- Every response carries `X-Request-ID`. Send your own `X-Request-ID` to correlate with the server logs.
- Authentication: none in the MVP. Deploy behind an authenticating proxy (see `07-deployment.md`).

## Error envelope

All non-2xx responses use the same shape:

```json
{
  "error": {
    "code": "FILE_TOO_LARGE",
    "message": "File exceeds the 10 MB limit.",
    "details": {"max_bytes": 10485760, "size_bytes": 12000000},
    "request_id": "3f9c2a71b0e44d1e"
  }
}
```

| HTTP | `code` | When |
|---|---|---|
| 400 | `EMPTY_FILE` | Zero-byte upload |
| 400 | `NO_LOG_CONTENT` | Whitespace only |
| 400 | `BINARY_CONTENT` | NUL bytes in the first 64 KB |
| 400 | `INVALID_ENCODING` | Not UTF-8 (`details.byte_offset`) |
| 404 | `NOT_FOUND` | Unknown analysis id |
| 409 | `NOT_READY` | Export requested before completion |
| 413 | `FILE_TOO_LARGE` | Exceeds `MAX_UPLOAD_MB` |
| 413 | `TOO_MANY_LINES` | Exceeds `MAX_LINES` |
| 415 | `UNSUPPORTED_FILE_TYPE` | Extension not in `.log`, `.txt`, `.jsonl` |
| 422 | `VALIDATION_ERROR` | Bad query/body (`details.errors`) |
| 500 | `INTERNAL_ERROR` | Unexpected; details only in server logs |

Analysis-level failures (`PIPELINE_ERROR`, `INTERRUPTED`) are reported on the analysis resource (`status: "failed"`, `error_code`, `error_message`), not as HTTP errors.

## Health

| Method | Path | Response |
|---|---|---|
| GET | `/health/live` | `200 {"status":"ok","version":"1.0.0"}` |
| GET | `/health/ready` | `200 {"status":"ok","database":"up","ai_provider":"mock"}` or `503 {"status":"unavailable","database":"down"}` |

## Configuration

`GET /api/v1/config` returns the public runtime settings. It never includes secrets.

```json
{
  "app_name": "LogLens AI", "version": "1.0.0", "environment": "production",
  "ai_provider": "mock", "ai_model": "loglens-mock-1", "ai_mode_label": "Mock AI (offline, deterministic)",
  "prompt_version": "incident-analysis/v1.0.0", "ai_timeout_seconds": 45.0, "ai_max_retries": 2,
  "evidence_token_budget": 6000, "max_upload_mb": 10.0, "max_lines": 200000,
  "allowed_extensions": [".log", ".txt", ".jsonl"], "retention_days": 30,
  "redaction_enabled": true, "redact_ip_addresses": true,
  "scenarios": [{"id": "pool_exhaustion", "description": "..."}]
}
```

## Analyses

### `POST /api/v1/analyses`

Multipart upload with field `file`. Returns `202 Accepted` immediately. Processing runs in the background.

```bash
curl -F "file=@app.log" http://localhost:8000/api/v1/analyses
```

```json
{"id": "06815dfc31e34b8cad318d6c6dbfdd13", "filename": "app.log", "status": "queued", "stage": "queued",
 "progress": 0, "error_code": null, "error_message": null, "created_at": "2026-10-26T06:55:53Z", "completed_at": null}
```

### `GET /api/v1/analyses/{id}/status`

Lightweight polling endpoint (same shape as above). `status`: `queued` → `processing` → `completed` | `failed`.
`stage` takes these values in order: `validating`, `parsing`, `aggregating`, `detecting_signals`, `selecting_evidence`, `saving_lines`, `ai_analysis`, `completed`.

### `GET /api/v1/analyses/{id}`

The full analysis. Abridged example (critical scenario, mock AI):

```json
{
  "id": "…", "status": "completed", "filename": "pool_exhaustion_1000.log", "total_lines": 1000,
  "errors": 161, "warnings": 16, "critical": 0, "malformed_lines": 0,
  "ai_status": "ok", "ai_provider": "mock", "ai_model": "loglens-mock-1",
  "prompt_version": "incident-analysis/v1.0.0", "confidence": "medium",
  "summary_lines": [
    "Incident: Database query timeouts after database connection pool exhaustion (order-service) (2026-03-14T09:00:01.787Z to 2026-03-14T09:21:32.530Z)",
    "Impact: 143 ERROR event(s) from order-service (…). Observed: 161 errors, 16 warnings, 0 critical events; 2 service(s) with errors.",
    "Evidence: L120 @ 2026-03-14T09:02:29.232Z WARN \"Connection pool usage reached 95%\" (critical signal); L303–L999 @ … 143× ERROR \"Database query timed out after <n>ms …\"; …",
    "Possible Cause (hypothesis, medium confidence, not confirmed): The WARN at L120 … preceded 143× ERROR events starting at L303; … [E1→L120, E2→L303–L999]",
    "Recommended Action: Check connection-pool metrics (active, idle, waiting) … Then: Inspect database latency, locks and slow-query logs …"
  ],
  "analysis": {
    "incident_title": "…", "impact": "…",
    "observed_facts": [{"statement": "…", "evidence_ids": ["E1"]}],
    "hypotheses": [{"statement": "…", "confidence": "medium", "rationale": "…", "evidence_ids": ["E1", "E2"]}],
    "recommendations": [{"action": "…", "priority": "immediate", "evidence_ids": ["E1"]}],
    "critical_evidence_ids": ["E1"], "overall_confidence": "medium", "uncertainty_notes": ["…"],
    "ai_status": "ok", "failure_reason": null, "provider": "mock", "model": "loglens-mock-1",
    "prompt_version": "incident-analysis/v1.0.0", "attempts": 1,
    "reattached_evidence_ids": [], "validation_warnings": [], "usage": {"input_tokens": 1400, "output_tokens": 900}
  },
  "evidence": {"items": [{"id": "E1", "kind": "precursor", "severity": "WARN", "count": 1, "first_line": 120, "last_line": 120,
    "line_refs": [120], "first_ts": "2026-03-14T09:02:29.232Z", "text": "Connection pool usage reached 95%",
    "must_include": true, "reason": "Rare WARN (occurs 1× in file); …; Precedes 143× ERROR database timeout starting at L303", "risk_score": 90}],
    "stats": {"…": "…"}, "omitted_group_count": 0, "token_estimate": 1403, "redaction_counts": {}},
  "signals": [{"kind": "precursor", "tags": ["rare_high_severity", "pattern", "threshold", "precursor"], "line_no": 120, "must_include": true, "…": "…"}],
  "groups": [{"template": "Database query timed out after <n>ms (…)", "severity": "ERROR", "count": 143, "risk_score": 67, "score_breakdown": {"severity": 30, "pattern": 20, "volume": 17}}],
  "stats": {"severity_counts": {"…": 0}, "timeline": [{"t": "…", "WARN": 0, "ERROR": 3, "CRITICAL": 0, "total": 40}], "…": "…"},
  "services": ["api-gateway", "auth-service", "…"],
  "redaction_counts": {}, "timings_ms": {"parse": 11.2, "aggregate": 16.5, "signals_stats": 3.0, "evidence": 2.1}
}
```

### `GET /api/v1/analyses?limit=20&offset=0`

History list, newest first: `{"items": [AnalysisListItem], "total": 42, "limit": 20, "offset": 0}`. Each item carries `incident_title`, the counts, `ai_status` and `confidence`.

### `GET /api/v1/analyses/{id}/lines`

Raw log search. All filters combine with AND.

| Param | Type | Notes |
|---|---|---|
| `q` | string ≤ 200 | Case-insensitive substring over message and raw line. `%` and `_` are matched literally. |
| `severity` | repeatable | `severity=ERROR&severity=WARN` |
| `service` | string | Exact service name |
| `malformed_only` | bool | Lines that could not be parsed |
| `line_numbers` | csv | `120,303,999` (max 500). Used to expand evidence. |
| `around_line` | int | Returns the page that contains this line under the current filters |
| `page`, `page_size` | int | `page_size` ≤ 500, default 100 |

Response: `{"items": [{"line_no": 120, "ts": "…Z", "severity": "WARN", "service": "order-service", "correlation_id": null, "message": "…", "raw": "…", "parse_ok": true, "is_continuation": false}], "total": 1, "page": 1, "page_size": 100}`.

### `GET /api/v1/analyses/{id}/export?format=json|markdown`

Returns an attachment (`<file>-incident.json` / `<file>-incident.md`). The JSON contains `summary_lines`, `analysis`, `critical_signals`, `evidence`, `stats` and `redaction_counts`. The Markdown is a human-readable incident report. Returns `409 NOT_READY` until the analysis is completed.

### `DELETE /api/v1/analyses/{id}`

`204 No Content`. Removes the analysis, its stored lines, groups and signals.

## Samples

| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/samples/analyze` | Body `{"scenario": "pool_exhaustion", "lines": 1000, "format": "text", "seed": 42}` → `202 AnalysisStatus`. `lines` 50–50,000. |
| GET | `/api/v1/samples/download?scenario=…&lines=…&format=text\|jsonl` | Synthetic file attachment |

Scenarios: `pool_exhaustion` (the critical regression scenario; line 120 is the 95% pool warning at 1,000 lines), `auth_attack`, `memory_leak`, `healthy`, `prompt_injection`. All sample data is fictional and generated from seeds.
