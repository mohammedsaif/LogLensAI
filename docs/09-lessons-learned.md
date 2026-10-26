# LogLens AI — Delivery Review & Lessons Learned

## 1. Feature completion matrix (against `01-prd.md`)

Status key: ✅ implemented and verified by automated tests · ◐ implemented with a stated limitation · ✗ not done.

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| FR-1 | Upload `.log/.txt/.jsonl`, configurable limits, secure validation | ✅ | `pipeline/validation.py`; `test_api.py` (7 rejection cases); E2E "invalid files" |
| FR-2 | Drag-and-drop + synthetic samples | ✅ | `Dropzone.tsx`, `samples/generator.py` (5 scenarios); RTL drop/keyboard tests; E2E sample flow |
| FR-3 | Timestamp, severity, service, message, correlation ID | ✅ | `pipeline/parser.py`; `test_parser.py` (28) |
| FR-4 | Text + JSON logs; raw lines preserved | ✅ | ISO, python-logging, syslog, JSON (pino levels, epoch); `raw` + `line_no` stored; malformed lines kept |
| FR-5 | Error/warning/critical counts, services, time range | ✅ | `pipeline/stats.py`; KPI cards |
| FR-6 | Duplicate detection & aggregation | ✅ | Templates + fingerprints; 143 timeouts → 1 group (regression test) |
| FR-7 | Preserve rare high-severity warnings | ✅ | `pipeline/signals.py` must_include rules; re-attachment in `analyzer.enforce_must_include` |
| FR-8 | DB timeout, pool exhaustion, auth, memory, service failure patterns | ✅ | `pipeline/patterns.py` (+ disk, rate limit); 13 positive and 9 negative pattern tests |
| FR-9 | Deterministic extraction before Claude | ✅ | Architecture; the evidence pack is the only AI input |
| FR-10 | Exactly five lines | ✅ | `ai/summary.py`; parametrized over 5 scenarios + fallback |
| FR-11 | Line numbers and timestamps in evidence | ✅ | Evidence line `L120 @ 2026-03-14T09:02:29.232Z …` |
| FR-12 | Facts vs hypotheses | ✅ | Separate schema fields; distinct UI styling; Markdown sections |
| FR-13 | Confidence without fabricated numbers | ✅ | Qualitative enum, caps, "not confirmed" label |
| FR-14 | Dashboard, charts, timeline, searchable logs, details | ✅ | Dashboard, Incident, Explorer pages |
| FR-15 | Inspect original evidence | ✅ | Expandable evidence → raw lines; `?line=` jump + highlight (E2E) |
| FR-16 | JSON + Markdown export | ◐ | Endpoint and UI verified. The real browser-download path was only exercised on Chromium in CI config (not run locally; see `06-testing.md` §7) |
| FR-17 | Invalid files, malformed lines, empty, AI timeouts, provider errors | ✅ | Error envelope + fallback tests |
| NFR | Performance targets | ✅ | 1k: 0.025 s; 50k: 1.2 s |
| NFR | Security (redaction, injection, no execution) | ✅ | `08-security.md`; redaction and injection suites |
| NFR | Accessibility | ◐ | Keyboard dropzone, ARIA progress/accordions/toggles, skip link, text alternatives for charts. **No automated axe audit was run.** |
| NFR | Runs with Docker Compose | ✅ | Verified locally on PostgreSQL 16 |
| NFR | Works without a paid API key | ✅ | Mock AI default, labelled in the UI |
| — | GitHub Actions CI | ◐ | Workflow written. Not executed (no remote). |
| — | Live Claude quality evaluation | ✗ | Requires a key and spend. Harness ready (`--provider anthropic`). |
| — | Authentication / multi-tenancy | ✗ | Out of MVP scope by design (PRD §8) |

## 2. Phase summaries

| Phase | Artifacts | Key decisions | Verification |
|---|---|---|---|
| 1 Discovery | `docs/01-prd.md` | Deterministic-first framing; acceptance criteria tied to tests | Reviewed against the final matrix (above) |
| 2 Design | `docs/02-architecture.md` | 8 ADRs (must_include re-attachment, code-rendered summary, qualitative confidence, BackgroundTasks MVP, portable SQL types) | Implemented as designed. The ER diagram matches the Alembic migration. |
| 3 UI/UX | `docs/03-ui-design.md` | Navy/teal; facts solid vs hypotheses dashed | Palette re-validated (CRITICAL moved to fuchsia, bar chart instead of donut); doc updated |
| 4 Backend | `backend/app/**` | FastAPI factory, versioned `/api/v1`, error envelope, JSON logs, health checks | 189 pytest tests, 98% coverage |
| 5 AI | `backend/app/ai/**`, `eval/` | Prompt v1.0.0; structured outputs; server-side fallbacks; retries owned by the app | Validation, injection and regression suites; eval 81/81 |
| 6 Frontend | `frontend/src/**` | TanStack Query for server state; shadcn-style primitives in-repo | 30 Vitest tests; manual review in the browser + screenshots |
| 7 Testing | tests, E2E, eval | Mocked AI everywhere | See `06-testing.md` |
| 8 DevOps | Dockerfiles, compose, CI, `.env.example` | Migrations in the entrypoint (skippable); non-root image; CSP | Compose up on PostgreSQL; migration down/up |
| 9 Docs | README + docs 01–09 | — | — |

## 3. Architecture walkthrough (for a reviewer)

1. **Upload** (`api/v1/analyses.py`): reads at most limit + 1 bytes and validates (`pipeline/validation.py`). It inserts an `analyses` row (`queued`), returns 202 and schedules `IncidentService.process`.
2. **Pipeline** (`pipeline/orchestrator.py`, run in a worker thread): `parser.parse_text` → `aggregator.enrich_records`/`aggregate` (templates, fingerprints, patterns, peak percentage) → `signals.detect_signals` (rules + explainable risk score) → `stats.compute_stats` → `evidence.build_evidence_pack` (redaction, must_include first, token budget). Progress is written to the row after each stage.
3. **Persistence**: raw lines, groups and signals are bulk-inserted for the explorer.
4. **AI** (`ai/analyzer.py`): fits the pack to the budget, renders `prompts/v1`, calls the provider with timeout and retries, extracts and validates JSON, checks references and certainty language, caps confidence, then `enforce_must_include`. Any failure → `heuristics.build_heuristic_analysis` with `ai_status=fallback`.
5. **Summary** (`ai/summary.py`): five lines from validated data plus deterministic counts. The analysis, summary and evidence are stored as JSON on the row.
6. **UI**: the progress page polls `/status`; the incident page renders the summary, the critical signals (first), KPIs, charts, facts/hypotheses, evidence (expands via `/lines?line_numbers=`) and exports. The explorer uses `/lines` with `around_line` for jumps.

## 4. Two-minute interview demo script

> **0:00 – Problem (15 s).** "In an incident, the clue is often one quiet warning buried under hundreds of repeated errors. Pasting logs into an LLM loses it, and the LLM may invent a root cause or leak secrets."
>
> **0:15 – Upload (20 s).** Open LogLens → Upload → drop `pool_exhaustion_1000.log` (1,000 lines). "Line 120 is a single `WARN Connection pool usage reached 95%`. Later there are 143 database timeouts." The progress page shows the stages: parsing, grouping, signals, redaction, AI.
>
> **0:35 – Five-line summary (30 s).** Point at the Evidence line: "`L120` comes first, flagged as a critical signal, then `143×` the timeout template." Point at Possible Cause: "a hypothesis with medium confidence, explicitly not confirmed, referencing E1→L120 and E2." Click `L120`, and the explorer opens highlighted on the original raw line.
>
> **1:05 – Why it's trustworthy (35 s).** Show the Critical signals panel: "Deterministic rules flagged this as rare, a threshold breach, and a precursor that precedes 143 errors. It is guaranteed to be in the output. If the model omits it, LogLens re-attaches it; if the AI times out, there's a deterministic fallback. A regression test fails if L120 ever disappears." Show the Privacy card: "Secrets are redacted before the model call." Mention the prompt-injection sample: "log lines that try to instruct the model are flagged and withheld."
>
> **1:40 – Engineering (20 s).** "FastAPI + PostgreSQL + React. Claude sits behind a provider abstraction, with structured outputs validated by Pydantic. A mock mode runs without a key. 189 backend tests at 98% coverage, 30 component tests, 10 Playwright E2E tests, and an eval set with 100% critical-signal recall. It runs with `docker compose up`."

## 5. Resume bullets (grounded in implemented functionality)

- Built **LogLens AI**, a FastAPI/PostgreSQL/React log-intelligence platform that turns 1,000+ log lines into an evidence-referenced five-line incident summary. Deterministic parsing, duplicate aggregation and a 7-pattern detection catalog run before a schema-validated Claude analysis. The pipeline processes 50k lines in ~1.2 s, after profiling cut it from 8.1 s.
- Designed a **critical-signal preservation layer** (precursor, threshold-breach and rarity rules, plus post-AI re-attachment). It guarantees that rare warnings, such as a 95% connection-pool warning hidden among 143 timeouts, survive token budgets, model omissions and AI outages. It is enforced by a regression suite and an evaluation set with 100% critical-signal recall (20/20).
- Hardened the LLM integration with **secret/PII redaction, prompt-injection detection and withholding**, non-forgeable evidence delimiters, Pydantic-validated structured outputs, bounded retries/timeouts and a deterministic fallback. Shipped it with 189 backend tests (98% coverage), 30 React Testing Library tests, Playwright E2E tests, Docker Compose and a GitHub Actions pipeline.

## 6. Lessons learned

1. **Test the deployment path early.** The settings bug (`CORS_ORIGINS` as JSON) passed every unit test and only showed up in `docker compose up`. A config test now covers the CSV and JSON forms.
2. **Scale tests reveal correctness bugs, not just speed problems.** The 200k-line run exposed unmasked all-letter hex IDs that split duplicate groups and created false "rare" signals.
3. **Look at the UI with real data.** Timezone-naive datetimes from SQLite and an overly broad `50[234]` regex were caught by looking at the explorer, not by tests. Both now have tests.
4. **Validate colors by computation.** The first severity palette failed a normal-vision separation check between ERROR and CRITICAL.
5. **Keep the model's job narrow.** Rendering the five lines in code made the format, counts and hypothesis labelling guaranteed rather than prompted.
6. **Tooling risk is real.** Playwright's Chromium download hung on this Windows/Node 24 setup. A `PW_CHANNEL` switch to the installed Edge kept the E2E suite runnable, but it surfaced an Edge-specific download/teardown quirk that needed a workaround.

## 7. Remaining issues / next steps

1. Run CI on GitHub (needs a remote) and confirm the Chromium E2E path, including real browser downloads.
2. Budget-capped live Claude evaluation (`eval.run_eval --provider anthropic`) and prompt iteration based on it.
3. Automated accessibility audit (axe-core in Playwright).
4. Job queue, authentication, and NER-based PII redaction (see the README roadmap).
5. Upgrade Recharts 2 → 3 (2.x is no longer actively maintained).
