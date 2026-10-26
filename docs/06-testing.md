# LogLens AI — Testing Strategy & Results

All results below were produced by actually running the commands on 2026-10-26 (Windows 11, Python 3.12.10, Node 24.16.0). AI calls in every automated test are **mocked**: no Anthropic API key was used, and nothing was billed.

## 1. Test pyramid

| Layer | Tool | Location | Count |
|---|---|---|---|
| Unit: parser & normalization | pytest | `backend/tests/test_parser.py` | 28 |
| Unit: patterns, aggregation, signals, scoring, stats | pytest | `backend/tests/test_detection.py` | 32 |
| Unit: evidence selection & token budget | pytest | `backend/tests/test_evidence.py` | 5 |
| Privacy / redaction | pytest | `backend/tests/test_redaction.py` | 16 |
| AI response validation, retries, timeouts, fallback | pytest + scripted providers | `backend/tests/test_ai_analyzer.py` | 23 |
| Prompt-injection | pytest | `backend/tests/test_prompt_injection.py` | 5 |
| Summary rendering + Anthropic adapter (fake SDK client) | pytest | `backend/tests/test_summary_provider.py` | 18 |
| Config & filename sanitization | pytest | `backend/tests/test_config.py` | 4 |
| API integration | FastAPI TestClient + SQLite | `backend/tests/test_api.py` | 29 |
| **Critical regression (L120 pool warning)** | pytest | `backend/tests/test_regression_pool_warning.py` | 18 |
| Performance + evaluation dataset | pytest (`-m performance`) | `backend/tests/test_performance_eval.py` | 11 |
| Frontend components & pages | Vitest + React Testing Library | `frontend/src/**/*.test.tsx` | 30 |
| End-to-end | Playwright | `frontend/e2e/*.spec.ts` | 10 |
| Offline evaluation harness | `python -m eval.run_eval` | `backend/eval/` | 81 checks |

## 2. Commands and actual results

```bash
cd backend
ruff check app tests eval && ruff format --check app      # All checks passed! / 45 files already formatted
pytest -q --cov=app --cov-report=term                     # 189 passed; TOTAL coverage 98%
python -m eval.run_eval                                   # Checks passed: 81/81; critical-signal recall 20/20

cd frontend
npx tsc --noEmit -p .                                     # no errors
npx vitest run --coverage                                 # 30 passed; line coverage 88.9 %
npx vite build                                            # built; chunks 99 kB app / 205 kB react / 384 kB charts (min)
PW_CHANNEL=msedge npx playwright test                     # 10 passed (≈ 37 s)
```

Coverage details: backend 98% of 1,912 statements (`pytest-cov`). The lowest backend module is `core/logging.py` (69%: the plain-text formatter branch is unused in tests). Frontend: 88.9% lines, 76.7% branches.

## 3. The critical regression test

`backend/tests/test_regression_pool_warning.py` builds the specified dataset (1,000 lines; line 120 = `WARN … Connection pool usage reached 95%`; 143 DB timeout errors later; verified by `test_dataset_shape`) in **text and JSONL** formats. It fails if the warning is missing from any of:

1. the deterministic signals (must be `must_include`, tagged precursor + threshold + rare, reason "Precedes 143× ERROR"),
2. the evidence pack **and the rendered prompt** (also at token budgets of 6,000, 800 and 50 with max 2 items),
3. the final incident analysis (`critical_evidence_ids`) with the mock model,
4. the analysis when a scripted model **ignores** the warning (re-attached, with an observed fact added),
5. the analysis when the AI **times out** (fallback),
6. the Evidence line of the five-line summary,
7. the API response end to end.

It also asserts that the 143 timeouts form **one** group with count 143 and the `db_timeout` pattern. The same scenario is covered in Playwright (`critical scenario …` tests) and in the evaluation dataset.

## 4. Mocked AI in CI

- `MockProvider` (offline, deterministic) runs the full parse → validate → render path.
- `ScriptedProvider` (tests) returns or raises a programmed sequence: valid JSON, fenced JSON, invalid JSON, schema violations, extra fields, unknown evidence IDs, certainty claims, `ProviderError` of each kind, hangs (timeouts) and unexpected exceptions.
- The Anthropic adapter is tested against a fake SDK client. The tests check request shape (`output_config.format`, `effort`, `betas`, `fallbacks`, timeout), the error mapping of real `anthropic` exception classes, and the `refusal`/`max_tokens` stop reasons.

## 5. Performance (measured)

Deterministic pipeline (parse → aggregate → signals → stats → evidence), best of 2 runs, same laptop:

| Lines | Time | Evidence items | Evidence tokens (est.) |
|---|---|---|---|
| 1,000 | 0.025 s | 5 | 1,287 |
| 10,000 | 0.23 s | 6 | 1,454 |
| 50,000 | 1.21 s | 7 | 1,635 |
| 200,000 | 5.6 s | — | — |

API end to end (upload → mock AI → persisted), from pytest budgets: 1,000 lines < 5 s and 20,000 lines < 20 s, both passing. The NFR targets (1k < 1 s, 50k < 15 s) are met with a wide margin.

Profiling fixed one hotspot along the way. The first version took 8.1 s for 50k lines; a keyword prefilter before the pattern regexes and a per-message template/pattern cache cut it to 1.2 s.

## 6. Defects found by testing (and fixed)

| # | Found by | Defect | Fix |
|---|---|---|---|
| 1 | Docker smoke test | Backend crashed at startup when `CORS_ORIGINS` was a plain comma-separated string (pydantic-settings parses list fields as JSON) | `NoDecode` + CSV/JSON validator; `tests/test_config.py` |
| 2 | Manual UI check in the browser | Explorer showed times shifted by +5:30: SQLite returns naive datetimes, serialized without `Z` | `UTCDateTime` response type; `test_datetimes_are_serialized_as_utc` |
| 3 | Manual UI check | `\b50[234]\b` matched "SKU-503" and "customer 502" (false service-failure patterns) | Status codes need HTTP context; 6 new tests |
| 4 | 200k-line performance probe | Correlation IDs consisting only of hex letters were not masked, splitting identical messages into one-off groups (false "rare" and "precursor" signals at scale) | Identifier keys always masked; regression test |
| 5 | Layout review (screenshots) | Critical-signal timestamp overlapped the message; evidence grid overflowed horizontally | Column width / `min-w-0` |
| 6 | Vitest | `scrollIntoView` missing in jsdom | Test setup stub |

## 7. Known failures, gaps and caveats

- **Playwright browser:** downloading the bundled Chromium (Playwright 1.49.0) **hung during archive extraction twice** on this machine (Node 24 on Windows). The E2E suite was therefore run against the installed **Microsoft Edge** via `PW_CHANNEL=msedge`. CI is configured for bundled Chromium on Linux (Node 22), which was **not executed** here.
- **Edge download quirk:** under headless Edge, any browser download caused Playwright to close the browser after the test, so the *next* test failed with `TargetClosedError`. The export E2E test therefore verifies the export links by fetching their URLs when `PW_CHANNEL` is set. The real browser-download branch only runs on bundled Chromium and **has not been executed locally**.
- **GitHub Actions** workflow is written but has **not run** (no remote).
- **No live Claude evaluation** was performed. The Anthropic provider is verified only against a fake client. `python -m eval.run_eval --provider anthropic` is ready but billed.
- Frontend tests assert chart presence and text alternatives, not pixel output. Charts were reviewed visually via screenshots.
- No load/concurrency test of many simultaneous uploads.
