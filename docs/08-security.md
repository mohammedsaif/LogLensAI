# LogLens AI — Security & Privacy

## 1. Principles

1. **Uploaded logs are untrusted input.** They are parsed as strings only and are never executed, evaluated, templated or passed to a shell.
2. **Logs are data, never instructions.** See the prompt-injection defenses in `05-ai-prompt-design.md` §8.
3. **Least data out.** Only a bounded, redacted evidence pack leaves the system, and only when a cloud provider is configured (`anthropic`, `openai` with a remote base URL, `gemini`). With `ollama` (or an OpenAI-compatible server on your own machine), nothing leaves your network. The Settings page shows where evidence is sent.
4. **Deterministic guarantees do not depend on the model.** Counts, line references and critical signals are computed in code.
5. **No secrets in the repo.** Configuration comes from the environment. `.env` is git-ignored and `.env.example` holds placeholders only.

## 2. Upload validation

| Check | Behavior |
|---|---|
| Extension allow-list | `.log`, `.txt`, `.jsonl` (`ALLOWED_EXTENSIONS`) → 415 |
| Filename | Reduced to its basename and stripped to `[A-Za-z0-9._- ]`, ≤ 120 chars (path traversal impossible; nothing is written to disk anyway) |
| Size | The server reads at most `MAX_UPLOAD_MB` + 1 byte → 413. nginx `client_max_body_size` is an outer guard. |
| Binary | NUL byte in the first 64 KB → 400 |
| Encoding | Strict UTF-8 (BOM tolerated) → 400 with byte offset |
| Line count | `MAX_LINES` → 413 |
| Line length | Lines > 10,000 chars are truncated in storage, with a marker |

## 3. Redaction (before any external model call)

`app/pipeline/redaction.py` runs on every evidence item's text and template. Each category counts hits, and the counts are stored and shown in the UI ("Privacy" card).

| Category | Example matched |
|---|---|
| `private_key` | `-----BEGIN RSA PRIVATE KEY-----…` |
| `url_credentials` | `postgres://user:pass@host` → `postgres://[REDACTED_CREDENTIALS]@host` |
| `jwt` | `eyJhbGciOi….….…` |
| `bearer_token` | `Authorization: Bearer abc…`, `Basic …`, `Token …` |
| `api_key` | `sk-…`, `sk-ant-…`, `AKIA…`/`ASIA…`, `ghp_…`, `xox?-…`, `AIza…`, `sk_live_…` |
| `secret_assignment` | `password=…`, `api_key: …`, `"client_secret": "…"`, `token=…`, `cookie=…` |
| `email` | `bob@example.com` |
| `card_number` | 13–19 digits **and** a valid Luhn checksum (so order IDs and timestamps are kept) |
| `ip_address` | IPv4 (toggle with `REDACT_IP_ADDRESSES`) |

Verified by `tests/test_redaction.py`, including an end-to-end test asserting that none of the planted secrets appear in the rendered prompt, and by the eval `forbidden_in_prompt` checks.

**Not redacted:** raw lines stored in the operator's database and shown in the explorer. The operator owns that data. Names, street addresses, phone numbers and free-form PII are **not** detected. A regex redactor cannot find these reliably, so see the limitations below.

## 4. Threat model summary

See `02-architecture.md` §7 for the full STRIDE table. Key residual risks:

| Risk | Residual | Mitigation path |
|---|---|---|
| No authentication in the MVP | High if exposed publicly | Deploy behind SSO / an authenticating reverse proxy / VPN (documented as required). RBAC is on the roadmap. |
| Regex redaction misses novel secret formats or unstructured PII | Medium | Add an entropy-based detector and allow-listed fields. Keep `AI_PROVIDER=mock`/`disabled` for highly sensitive logs. |
| Heuristic injection detection misses novel phrasing | Low–Medium | Layered defenses bound the impact (no tools, schema, code-rendered summary, re-attached signals). |
| In-process background jobs | Low | DoS via many concurrent uploads is limited only by the server. Add rate limiting at the proxy. |

## 5. Transport & headers

- The nginx frontend sets `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` and a restrictive `Content-Security-Policy` (`default-src 'self'`, no inline scripts).
- The API sets `X-Content-Type-Options` and `Referrer-Policy`. CORS is restricted to `CORS_ORIGINS`.
- TLS is terminated at the ingress / load balancer (see `07-deployment.md`).
- React escapes all model and log text. The codebase has no `dangerouslySetInnerHTML`.

## 6. Secrets handling

- `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` and `GEMINI_API_KEY` are `SecretStr`. They are never logged and never returned by `/api/v1/config` (asserted by `test_config_exposes_no_secrets` and `test_config_endpoint_per_provider`).
- The Anthropic SDK logger is pinned to WARNING, so request bodies are not logged.
- Docker Compose requires `POSTGRES_PASSWORD` from `.env` (`${POSTGRES_PASSWORD:?…}`), so a default password cannot be shipped silently.
- The CI uses a throwaway Postgres password scoped to the job.

## 7. Data retention

- `RETENTION_DAYS` (default 30) purges analyses at startup. `DELETE /api/v1/analyses/{id}` removes one analysis immediately, with its lines, groups and signals.
- Mock and disabled modes send nothing externally. With Anthropic, the redacted evidence pack is subject to the provider's data-handling terms.

## 8. Supply chain

- All backend dependencies are pinned (`requirements.txt`). Frontend dependencies are pinned in `package.json` and locked by `package-lock.json`.
- Containers run as a non-root user (backend), with slim/alpine base images and multi-stage builds.
- Recommended additions: Dependabot/Renovate, `pip-audit`, `npm audit` in CI, and image scanning (Trivy).
