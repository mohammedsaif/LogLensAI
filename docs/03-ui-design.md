# LogLens AI — UI/UX Design

## 1. Design principles

1. **Signal before volume.** Critical warnings are shown above the charts. A single precursor line is visually louder than 143 repeated errors.
2. **Every claim is inspectable.** Line numbers are links. Evidence expands inline to the original raw lines.
3. **Facts and guesses look different.** Observed facts use solid badges. Hypotheses use dashed outlines and an explicit "Hypothesis" label with a confidence chip.
4. **Honest system state.** Mock AI mode and fallback summaries are announced with banners, never hidden.
5. **Calm, dense, professional.** A SaaS look with navy chrome, teal accents and neutral surfaces.

## 2. Visual language

| Token | Value | Use |
|---|---|---|
| `navy-950` | `#0b1426` | Sidebar background |
| `navy-900` | `#0f1d36` | Headings, primary text on light |
| `navy-700` | `#1e3a64` | Secondary chrome |
| `teal-600` | `#0d9488` | Primary actions, active nav, focus ring |
| `teal-50` | `#f0fdfa` | Selected / highlight surfaces |
| `slate-50` | `#f8fafc` | App background |
| `slate-200` | `#e2e8f0` | Borders |
| `slate-500` | `#64748b` | Muted text |
| Severity CRITICAL | `#a21caf` (fuchsia-700) | Chart; badge uses fuchsia-100/900 |
| Severity ERROR | `#dc2626` (red-600) | Badge, chart |
| Severity WARN | `#ca8a04` (yellow-600) | Chart; badge uses amber-100/900 |
| Severity INFO | `#0d9488` (teal-600) | Badge, chart |
| Severity DEBUG / UNKNOWN | `#94a3b8` (slate-400) | Badge, chart |

- **Typography:** Inter (system fallback). 14 px base, 12 px for dense tables, monospaced (`JetBrains Mono`, `ui-monospace`) for raw log lines and line numbers.
- **Radius** 8 px for cards, 6 px for controls. **Shadows** subtle (`shadow-sm`). **Spacing** on a 4 px grid.
- **Contrast:** every text/background pair meets 4.5:1. Severity is never conveyed by color alone: badges always carry the text label.
- **Chart palette validation:** the WARN/ERROR/CRITICAL series colors were checked with a palette validator (lightness band, chroma, CVD and normal-vision separation). The first choice (amber/red/rose) failed normal-vision separation between ERROR and CRITICAL, so CRITICAL moved to fuchsia and WARN to yellow-600. Yellow is below 3:1 against white, so the charts carry visible value labels, a legend and tooltips.

## 3. Information architecture

```
┌ Sidebar (navy) ─────────┐┌ Top bar: page title · AI mode chip ───────────────┐
│ ◆ LogLens AI            ││                                                   │
│ ▸ Dashboard             ││                 Page content                      │
│ ▸ Upload Logs           ││                                                   │
│ ▸ Incident History      ││                                                   │
│ ▸ Settings              ││                                                   │
│                         ││                                                   │
│ (Analysis pages appear  ││                                                   │
│  in context: Progress,  ││                                                   │
│  Summary, Raw Logs)     ││                                                   │
└─────────────────────────┘└───────────────────────────────────────────────────┘
```

Routes:

| Route | Page |
|---|---|
| `/` | Dashboard (latest completed analysis, or an empty state) |
| `/upload` | Upload Logs |
| `/analyses/:id/progress` | Analysis Progress |
| `/analyses/:id` | Incident Summary |
| `/analyses/:id/logs` | Raw Log Explorer (`?line=120` scrolls to and highlights a line) |
| `/history` | Incident History |
| `/settings` | Settings |

## 4. Pages

### 4.1 Dashboard
- **KPI row** (4 cards): Total lines · Errors · Warnings · Critical. A subline shows affected services and the time range.
- **Critical signals strip:** the top must-include signals, each with a line link.
- **Charts:** severity distribution (horizontal bars with value labels; bars read magnitudes better than a donut) and a timeline (stacked area per bucket: WARN/ERROR/CRITICAL, showing only severities that occur).
- **Latest summary card** with the five lines and a link to the full incident.
- **Empty state:** illustration-free card: "No analyses yet", with a primary "Upload logs" button and a secondary "Try a sample incident" button.

### 4.2 Upload Logs
- Large dashed **dropzone** with keyboard support (Enter/Space opens the file picker). Accepts `.log,.txt,.jsonl` and shows the size limit from `/api/v1/config`.
- Client-side pre-validation (extension, size, empty) with inline error text (`role="alert"`).
- **Sample generator panel:** scenario select (Connection pool exhaustion, Authentication attack, Memory leak, Healthy baseline, Prompt-injection probe), line-count input (100–50,000), "Analyze sample" button and "Download sample" button.
- After submit, navigate to Analysis Progress.

### 4.3 Analysis Progress
- A stage list (Validating → Parsing → Aggregating → Detecting signals → Selecting evidence → AI analysis → Saving), each with a done, active or pending icon.
- A progress bar with `aria-valuenow`, and an `aria-live="polite"` text update.
- Redirects to the Incident Summary when completed. On `failed`, shows an error card with the code, message, "Try again" and "Back to upload".

### 4.4 Incident Summary
- **Header:** filename, created time, status chips (AI: Claude / Mock / Fallback), confidence chip, Export menu (JSON, Markdown).
- **Fallback / mock banner** when applicable, with the reason.
- **Five-line summary card:** a label column (Incident, Impact, Evidence, Possible Cause, Recommended Action) and a value column. Line refs such as `L120` are links to the explorer. Possible Cause has a dashed border, a "Hypothesis" badge and a confidence chip.
- **Critical warnings panel** (amber/rose accent): every must-include signal, with severity, line, timestamp, reason ("Rare WARN, pool pressure precursor before 143 DB timeouts") and an "Inspect" link.
- **Observed facts** vs **Hypotheses** in two columns, each item listing its evidence chips (`E3 · L120`).
- **Evidence list:** accordion items (`<button aria-expanded>`). The header shows the ID, severity, count, line range and template. The body lists the original raw lines in monospace, with line numbers that link to the explorer.
- **Charts:** severity distribution and timeline. **Top event groups** table.
- **Recommendations** list with priority badges. **Uncertainty notes.** **Redaction report** (counts by category).

### 4.5 Raw Log Explorer
- Toolbar: search input (debounced 300 ms), severity multi-toggle, service select, "Malformed only" toggle, result count.
- A virtual-feeling paged table (100 rows per page): line no, timestamp, severity badge, service, message. Expanding a row shows the raw line and the correlation ID.
- `?line=N` jumps to the right page and highlights the row with a teal-50 background.
- Empty state: "No lines match these filters", with a "Clear filters" button.

### 4.6 Incident History
- A table of analyses: filename, created, status, lines, errors, confidence, AI mode, and actions (Open, Delete with confirm).
- Empty state with an upload call to action. Pagination.

### 4.7 Settings
- **Server settings (read-only):** AI provider, model, prompt version, timeout, retries, max upload size, max lines, retention days, redaction enabled.
- **Client preferences (stored in `localStorage`):** polling interval, default explorer page size, compact tables.
- An explanation of mock mode and how to enable Claude (`AI_PROVIDER=anthropic`, `ANTHROPIC_API_KEY`).

## 5. States

| State | Pattern |
|---|---|
| Loading | Skeleton blocks matching the final layout. Spinners only inside buttons. |
| Empty | Neutral card with one sentence and a primary action. |
| Error (request) | Red-bordered card with `role="alert"`, error code, message and retry. |
| Error (analysis failed) | A Progress page variant with the failure stage highlighted. |
| Degraded (AI fallback) | Amber banner: "AI analysis unavailable (timeout). Showing deterministic summary." |
| Mock mode | Teal info chip in the top bar: "Mock AI": "Summaries are generated by a deterministic offline model". |

## 6. Responsive layout

| Breakpoint | Layout |
|---|---|
| < 768 px | Sidebar collapses into a top bar with a menu button (drawer). KPI cards in 2×2. Charts stack. The explorer hides the service column. Summary labels sit above their values. |
| 768–1279 px | Sidebar is an icon rail plus labels. KPI 4-up. Charts 1-up. |
| ≥ 1280 px | Full sidebar. Charts 2-up. Facts and hypotheses side by side. |

## 7. Accessibility checklist

- Every interactive element is reachable with Tab and has a visible `focus-visible` ring (teal, 2 px).
- The dropzone is a `<button>`-role region with a descriptive `aria-label`. A hidden file input has a `<label>`.
- Accordions use `aria-expanded` / `aria-controls`.
- Progress uses `role="progressbar"` and the live region announces stage changes.
- Charts have `aria-label` summaries and a text table alternative (KPI and severity counts are also rendered as text).
- Color is never the only carrier of meaning (severity text labels, hypothesis badge text).
- `prefers-reduced-motion` disables transitions.
