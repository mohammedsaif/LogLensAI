# LogLens AI — Product Requirements Document

| | |
|---|---|
| Status | MVP implemented (see feature matrix in `docs/09-lessons-learned.md`) |
| Owner | Engineering (single-team MVP) |
| Last updated | 2026-10-26 |

## 1. Problem statement

When an incident starts, on-call engineers get a log file with thousands of lines. The real signal is buried. Usually it is a burst of identical errors plus one or two early warnings that came *before* the burst. People skim the file, grep for `ERROR`, and miss the low-volume precursor, for example `WARN Connection pool usage reached 95%`. That precursor is often what explains the outage.

Generic "paste the log into an LLM" workflows make this worse:

- Large files exceed context windows, so the model only sees a truncated slice.
- Models summarize by volume, so a single warning gets lost under 143 timeouts.
- Models may present a guess as a confirmed root cause.
- Raw logs contain secrets, tokens and personal data that should not leave the network.
- Logs are untrusted input: a log line can contain text that tries to instruct the model.

## 2. Product vision

**Turn 1,000+ log lines into an actionable five-line incident summary, without losing rare but critical warning signals.**

LogLens AI is a deterministic-first pipeline. Parsing, counting, grouping, pattern detection and critical-signal preservation all happen in plain Python with test coverage. The LLM (Claude) only interprets a small, redacted, referenced evidence pack. Its output is schema-validated and rendered into a fixed five-line format.

## 3. Target users

- On-call / SRE engineers who triage production incidents.
- Backend developers who debug failures in their own services.
- Engineering managers / incident commanders who need a fast, honest status line.
- Support engineers who receive log bundles from customers.

## 4. Personas

| Persona | Context | Needs | Frustrations |
|---|---|---|---|
| **Priya, SRE on call** | Paged at 02:00. Has a 5 MB log export from three services. | A trustworthy summary in under a minute, with line numbers to verify. | Grep finds 143 timeouts and nothing about why. LLM tools invent root causes. |
| **Marcus, backend developer** | Owns `order-service`. Gets a ticket with an attached `.jsonl`. | See which services and patterns are involved, then jump to the raw lines. | JSON logs are hard to read. Duplicate stack traces hide the first occurrence. |
| **Dana, incident commander** | Runs the incident call and needs to brief stakeholders. | A plain-language Incident / Impact / Cause / Action, with the confidence stated honestly. | Engineers overstate certainty. Status updates take too long to write. |
| **Leo, security-minded platform lead** | Approves tooling. | Proof that secrets are redacted before external calls and that logs cannot steer the AI. | Tools that ship raw logs to third parties. |

## 5. User stories

| ID | Story | Priority |
|---|---|---|
| US-1 | As an SRE, I can drag and drop a `.log`, `.txt` or `.jsonl` file and get an analysis without configuration. | Must |
| US-2 | As a user, I can generate a synthetic sample log so I can try the product without real data. | Must |
| US-3 | As an SRE, I see counts of errors, warnings and critical events, affected services and the time range. | Must |
| US-4 | As an SRE, I see repeated errors collapsed into groups with counts and first/last occurrence. | Must |
| US-5 | As an SRE, I am guaranteed to see rare high-severity warnings even when they are drowned out by volume. | Must |
| US-6 | As an SRE, I get a five-line summary: Incident, Impact, Evidence, Possible Cause, Recommended Action. | Must |
| US-7 | As an SRE, every claim links to original line numbers and timestamps that I can inspect. | Must |
| US-8 | As an incident commander, I can tell observed facts from hypotheses and see a qualitative confidence level. | Must |
| US-9 | As a developer, I can search and filter raw log lines by text, severity and service. | Must |
| US-10 | As a user, I can export the analysis as JSON or Markdown. | Must |
| US-11 | As a user, I see clear messages for invalid files, empty uploads and AI outages, and still get a deterministic summary. | Must |
| US-12 | As a platform lead, I can verify that secrets and emails are redacted before any external model call. | Must |
| US-13 | As a user, I can revisit previous analyses in an incident history. | Should |
| US-14 | As a developer, I can run everything locally without a paid API key (mock AI mode). | Must |
| US-15 | As a user, I can view runtime settings (AI mode, limits) in the UI. | Should |

## 6. Functional requirements

| ID | Requirement |
|---|---|
| FR-1 | Upload `.log`, `.txt`, `.jsonl` files. Size limit is configurable (`MAX_UPLOAD_MB`, default 10 MB). Validate extension, size, UTF-8 decodability, binary content (NUL bytes) and line count (`MAX_LINES`). |
| FR-2 | Drag-and-drop upload. One-click synthetic sample generation (scenario and line count selectable). |
| FR-3 | Parse timestamp, severity, service, message and correlation ID where available. |
| FR-4 | Support common text formats (ISO-8601, `YYYY-MM-DD HH:MM:SS,mmm`, syslog-style) and JSON lines. Preserve every raw line with its 1-based line number. |
| FR-5 | Compute error, warning and critical counts, affected services and time range. |
| FR-6 | Fingerprint messages (numbers, IDs, IPs, durations masked) and aggregate duplicates into event groups. |
| FR-7 | Deterministically flag rare high-severity events and mark them `must_include`. |
| FR-8 | Detect patterns: database timeout, connection pool exhaustion / pressure, authentication failure, memory pressure / OOM, service failure / unavailability, plus disk and rate limiting. |
| FR-9 | Build a redacted evidence pack from deterministic results before any AI call. |
| FR-10 | Produce exactly five summary lines: Incident, Impact, Evidence, Possible Cause, Recommended Action. |
| FR-11 | Evidence references include original line numbers and timestamps. |
| FR-12 | Observed facts and hypotheses are separate fields and are rendered differently. |
| FR-13 | Confidence is qualitative (`low` / `medium` / `high`) with uncertainty notes. No fabricated percentages. |
| FR-14 | Dashboard: KPI cards, severity distribution, timeline, searchable logs, incident details. |
| FR-15 | Every evidence item expands to its original raw lines. |
| FR-16 | Export JSON and Markdown. |
| FR-17 | Graceful handling of invalid files, malformed lines, empty uploads, AI timeouts and provider errors, with a deterministic fallback summary. |

## 7. Nonfunctional requirements

| Category | Requirement |
|---|---|
| Performance | 1,000-line file is processed by the deterministic pipeline in < 1 s. A 50,000-line file in < 15 s on a developer laptop (excluding the AI call). |
| AI latency | AI call timeout is configurable (default 45 s), with at most 2 retries. The total AI budget is bounded. |
| Reliability | An AI failure never fails an analysis. The deterministic fallback is always produced. |
| Security | Uploaded content is untrusted. Secrets are redacted before external calls. No log content is executed. Prompt-injection markers are detected and flagged. |
| Privacy | Raw logs are stored only in the operator's own database. Retention is configurable (`RETENTION_DAYS`). Only redacted evidence leaves the system. |
| Accessibility | WCAG 2.1 AA intent: keyboard-operable controls, visible focus, labelled inputs, sufficient contrast, ARIA live regions for progress. |
| Observability | Structured JSON logs with request IDs. `/health/live` and `/health/ready` endpoints. |
| Portability | Runs with `docker compose up`. Runs locally without a paid API key (mock AI mode). |
| Maintainability | Modular pipeline stages, typed code (Pydantic / TypeScript), automated tests in CI. |

## 8. MVP scope

**In scope:** everything in section 6, single-tenant deployment, PostgreSQL persistence, mock and Anthropic providers, Docker Compose, GitHub Actions CI.

**Explicitly excluded from the MVP:**

- Authentication, multi-tenancy, RBAC. Deploy behind an authenticating proxy or VPN.
- Live log streaming / agents / integrations (Datadog, Loki, CloudWatch).
- Durable job queue. Analyses run as in-process background tasks. A restart marks in-flight jobs as failed.
- Multi-file correlation across uploads.
- Alerting and notifications.
- Fine-tuned or self-hosted models.

## 9. Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| AC-1 | Uploading a valid 1,000-line file returns an analysis with status `completed` and exactly five summary lines. | `test_api.py`, Playwright |
| AC-2 | In the critical scenario (pool warning at line 120, 143 DB timeouts later), line 120 appears in the critical signals, in the evidence pack, in the final analysis and in the Evidence summary line. | `test_regression_pool_warning.py` |
| AC-3 | The 143 timeouts are aggregated into one group with count 143. | `test_regression_pool_warning.py` |
| AC-4 | Empty, binary, oversized and wrong-extension files are rejected with a 4xx and a readable message. | `test_api.py`, `test_validation.py` |
| AC-5 | Malformed lines are counted and preserved, and do not fail the analysis. | `test_parser.py` |
| AC-6 | With the provider timing out or returning invalid JSON, the analysis completes with `ai_status = fallback` and a deterministic summary. | `test_ai_analyzer.py` |
| AC-7 | Emails, bearer tokens, API keys, passwords and credentialed URLs never appear in the prompt sent to the provider. | `test_redaction.py` |
| AC-8 | A log line saying "ignore previous instructions" is flagged and does not change the system prompt or the output schema. | `test_prompt_injection.py` |
| AC-9 | The Possible Cause line is always labelled as a hypothesis and never says "confirmed". | `test_summary.py` |
| AC-10 | JSON and Markdown exports download and contain the five lines and the evidence references. | `test_api.py`, Playwright |

## 10. Success metrics

| Metric | Target | How measured |
|---|---|---|
| Critical-signal recall on the evaluation dataset | 100 % of labelled must-find signals | `backend/eval/run_eval.py` |
| Pattern detection recall on the evaluation dataset | ≥ 95 % | `run_eval.py` |
| Time from upload to summary, 1,000 lines, mock AI | < 2 s | performance test |
| Analyses completing without error, including AI outages | 100 % | fallback tests |
| User-reported "summary was misleading" | < 5 % of analyses | post-MVP feedback widget (not built) |

## 11. Assumptions

- Log files are UTF-8 (BOM tolerated). Other encodings are rejected with a clear message.
- One file is one incident window. Users pre-filter huge archives.
- Timestamps without a timezone are treated as UTC.
- Severity keywords follow common conventions (`WARN`/`WARNING`, `ERR`/`ERROR`, `FATAL`/`CRITICAL`).
- Operators provide their own Anthropic API key and accept that redacted evidence is sent to Anthropic.

## 12. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| LLM omits a critical warning | Medium | High | Deterministic `must_include` signals are re-attached after AI validation. Covered by a regression test. |
| LLM hallucinates a root cause | Medium | High | Cause is always a hypothesis with a confidence label. Evidence IDs are validated. The word "confirmed" is rejected. |
| Prompt injection via log content | Medium | Medium | Evidence is JSON-encoded inside delimiters. Injection markers are flagged. No tools are granted. Output schema is validated. |
| Secrets leaked to the provider | Medium | High | Redaction runs before evidence selection. Tests cover common secret formats. |
| Unknown log formats parse poorly | High | Medium | A best-effort parser keeps raw lines. Malformed lines are counted and shown. |
| Large files exhaust memory | Low | Medium | Upload size and line-count limits. Streaming decode. |
| In-process background tasks lost on restart | Medium | Low | Documented. Startup marks stale `processing` jobs as failed. Queue is on the roadmap. |
