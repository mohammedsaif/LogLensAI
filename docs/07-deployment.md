# LogLens AI — Deployment, Operations, Rollback

## 1. Artifacts

| Artifact | Built from | Runtime |
|---|---|---|
| `loglens-backend` image | `backend/Dockerfile` (python:3.12-slim, multi-stage, non-root `app` user) | `docker-entrypoint.sh` runs `alembic upgrade head`, then uvicorn on :8000 |
| `loglens-frontend` image | `frontend/Dockerfile` (node:22-alpine build → nginx:1.27-alpine) | nginx on :8080 serves the SPA, proxies `/api` and `/health` to `backend:8000` |
| PostgreSQL 16 | `postgres:16-alpine` | Named volume `pgdata` |

## 2. Local: Docker Compose (verified)

```bash
cp .env.example .env          # set POSTGRES_PASSWORD; keep AI_PROVIDER=mock for no-cost use
docker compose up --build -d
open http://localhost:8080    # UI
curl localhost:8080/health/ready
```

Verified in this build (Docker 29.8.1, Windows): all three containers healthy. Alembic revision `0001` applied on PostgreSQL. `alembic downgrade base && alembic upgrade head` succeeded. A 1,000-line upload completed with L120 preserved. The CSP and frame headers are present.

To enable Claude: set `AI_PROVIDER=anthropic` and `ANTHROPIC_API_KEY=…` in `.env`, then run `docker compose up -d backend`. Claude calls are billed per token. The evidence pack is ~1.5–6k input tokens per analysis.

## 3. Local without Docker

```bash
# backend (SQLite by default; tables auto-created for SQLite)
cd backend
python -m venv .venv && .venv/Scripts/activate         # Windows   (Linux/macOS: source .venv/bin/activate)
pip install -r requirements-dev.txt
uvicorn app.main:create_app --factory --reload --port 8000

# frontend (separate terminal; Vite proxies /api to :8000)
cd frontend
npm ci
npm run dev                                             # http://localhost:5173
```

For PostgreSQL locally, set `DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/loglens` and run `alembic upgrade head`.

## 4. Production deployment guide

LogLens is a stateless API, a static SPA and a PostgreSQL database. Any container platform works: ECS/Fargate, Cloud Run, Kubernetes, Fly.io, or a single VM running Compose.

1. **Database:** a managed PostgreSQL 16 (RDS, Cloud SQL, Azure Flexible Server) with automated backups and point-in-time recovery enabled.
2. **Secrets:** store `DATABASE_URL`, `ANTHROPIC_API_KEY` and `POSTGRES_PASSWORD` in the platform secret manager. Inject them as environment variables. Never bake them into images.
3. **Migrations:** run `alembic upgrade head` as a one-off release job before rolling the new backend version (set `SKIP_MIGRATIONS=1` on the long-running backend containers in that setup). Migrations must stay backward-compatible with the previous app version (expand → migrate → contract).
4. **Backend:** ≥ 2 replicas behind the load balancer. Readiness probe `GET /health/ready`, liveness probe `GET /health/live`. Resources ≈ 0.5 vCPU / 512 MB per replica for 10 MB uploads.
5. **Frontend:** serve the nginx image, or upload `frontend/dist` to a CDN and route `/api/*` to the backend.
6. **Ingress:** TLS termination, an **authenticating proxy (SSO/OIDC) or VPN is required**, since the MVP has no user auth. Set a body limit ≥ `MAX_UPLOAD_MB` and a rate limit on `POST /api/v1/analyses`.
7. **CORS:** set `CORS_ORIGINS` to the public UI origin.
8. **Observability:** the backend logs JSON to stdout (`request_id`, `analysis_id`, `ai_status`, durations). Ship the logs to your aggregator. Alert on `analysis_failed` and on the share of `ai_status="fallback"`.
9. **Scaling note:** analyses run as in-process background tasks. With multiple replicas, each analysis runs on the replica that received the upload. Status polling works from any replica because state lives in PostgreSQL. A replica restart marks its in-flight analyses `INTERRUPTED`. Move to a job queue before high-volume use.

### Environment variables

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./loglens.db` | `postgresql+psycopg://…` in production |
| `AI_PROVIDER` | `mock` | `mock` \| `anthropic` \| `openai` \| `gemini` \| `ollama` \| `disabled` |
| `ANTHROPIC_API_KEY` | – | Required for `anthropic` |
| `ANTHROPIC_MODEL` | `claude-opus-5-5` | |
| `ANTHROPIC_EFFORT` | `medium` | `low` … `max` |
| `ANTHROPIC_SERVER_FALLBACKS` | `true` | Server-side refusal fallback |
| `OPENAI_API_KEY` / `OPENAI_MODEL` / `OPENAI_BASE_URL` | – | Model required. Base URL for OpenAI-compatible servers. |
| `OPENAI_RESPONSE_FORMAT` | `json_schema` | `json_object` for servers without JSON-schema support |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | – | Both required for `gemini` |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` / `OLLAMA_NUM_CTX` | `http://localhost:11434` / `llama3.1:8b` / `16384` | In Docker Compose the backend uses `OLLAMA_DOCKER_URL` (default `http://host.docker.internal:11434`) |
| `AI_TIMEOUT_SECONDS` / `AI_MAX_RETRIES` | `45` / `2` | |
| `AI_MAX_OUTPUT_TOKENS` | `4000` | |
| `EVIDENCE_TOKEN_BUDGET` / `EVIDENCE_MAX_ITEMS` | `6000` / `25` | |
| `MAX_UPLOAD_MB` / `MAX_LINES` | `10` / `200000` | Keep nginx `client_max_body_size` ≥ this |
| `RARE_MAX_COUNT` / `THRESHOLD_PERCENT` / `BURST_MIN_COUNT` | `3` / `80` / `10` | Detection tuning |
| `REDACT_IP_ADDRESSES` | `true` | |
| `RETENTION_DAYS` | `30` | `0` disables the purge |
| `CORS_ORIGINS` | localhost dev origins | Comma-separated or a JSON list |
| `LOG_LEVEL` / `LOG_JSON` | `INFO` / `true` | |

## 5. CI/CD

`.github/workflows/ci.yml` (written; **not executed** in this build because no GitHub remote was configured):

| Job | Steps |
|---|---|
| backend | ruff lint + format check → pytest with coverage (fails under 90%) → offline eval |
| migrations | Postgres service → `alembic upgrade/downgrade/upgrade` → API smoke test checking L120 in the Evidence line |
| frontend | `npm ci` → typecheck → vitest with coverage → build |
| e2e | backend + frontend → Playwright (Chromium) |
| docker | builds both images |

Suggested CD: on a tag, build and push the images (`ghcr.io/<org>/loglens-*:<sha>`), run the migration job, roll out the backend, then the frontend.

## 6. Rollback

| Situation | Action |
|---|---|
| Bad backend release, no schema change | Redeploy the previous image tag. |
| Bad release with a migration | 1) Redeploy the previous backend image (expand-only migrations keep it compatible). 2) Only if required: `alembic downgrade <previous_revision>` from the release job. **Back up first**, because downgrades can drop columns or data. |
| AI provider incident / cost spike | Set `AI_PROVIDER=mock` or `disabled` and restart. Analyses continue with deterministic summaries. No data migration needed. |
| Frontend regression | Redeploy the previous frontend image or CDN version. The API is versioned (`/api/v1`). |
| Corrupted data | Restore PostgreSQL from PITR to a new instance and repoint `DATABASE_URL`. |

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Backend container `unhealthy`, `SettingsError … cors_origins` | Malformed list env var (fixed in 1.0.0: comma-separated values are accepted) | Use `CORS_ORIGINS=http://a,http://b` or a JSON list |
| `/health/ready` returns 503 | Database unreachable / wrong `DATABASE_URL` | Check credentials, network and `docker compose logs db` |
| Every analysis shows "Deterministic fallback: AI provider not configured: …" | Missing key or model for the selected provider | The reason names the missing variable. Set it, or switch to `mock`. |
| Fallback reason "Cannot reach Ollama" | `ollama serve` not running, or the wrong URL from Docker | Start Ollama. In Compose, keep `OLLAMA_DOCKER_URL=http://host.docker.internal:11434`. |
| Fallback reason "Model 'x' is not available" | Model not pulled | `ollama pull x` |
| Local model analyses often fall back with "AI output failed validation" | Small model (about 3B) cannot follow the schema/rules | Use a 7B+ model or a cloud provider. Facts and critical signals are still correct. |
| Fallback reason "AI request timed out" | Slow provider / large pack | Raise `AI_TIMEOUT_SECONDS` or lower `EVIDENCE_TOKEN_BUDGET` |
| Upload returns 413 at the proxy before reaching the API | nginx `client_max_body_size` < `MAX_UPLOAD_MB` | Align both values |
| Analyses stuck, then `INTERRUPTED` after a restart | In-process jobs lost on restart | Re-upload. Plan the queue migration. |
| Timestamps look shifted in the UI | Logs without a timezone are interpreted as UTC (documented assumption) | Emit offsets in your logs |
| `entrypoint: not found` in the backend container | `docker-entrypoint.sh` checked out with CRLF | `.gitattributes` forces LF. Re-checkout or run `dos2unix`. |
