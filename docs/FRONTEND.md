# Frontend (Workstream 4)

React 19 + TypeScript + Vite + Tailwind CSS v4, in `frontend/`. For using the app, see [USER_GUIDE.md](USER_GUIDE.md). For the visual rules, see [frontend/DESIGN.md](../frontend/DESIGN.md).

## Run

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev          # Vite dev server (team uses port 5180: npm run dev -- --port 5180)
npm test             # vitest, ~170 tests
npm run typecheck    # tsc -b --noEmit
npm run lint         # oxlint
npm run build        # production build to dist/
```

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `VITE_USE_MOCKS` | `true` | Anything but `"false"` serves `/api/analyze`, `/api/llm/refine`, `/api/rules`, `/api/audiences` from `services/mockData.ts`. |
| `VITE_API_BASE_URL` | empty (same origin) | Integrated FastAPI backend (`backend/api/main.py`), e.g. `https://rtjsllveri.execute-api.us-east-1.amazonaws.com`. |
| `VITE_RAG_API_URL` | live WS1 API | RAG API for guideline excerpts (`/api/rag/context`, `/api/rag/retrieve`). Used even in mock mode; falls back to mock excerpts on failure. If empty, uses `VITE_API_BASE_URL`. |

To go live once Task I.5 is deployed: `VITE_USE_MOCKS=false` and `VITE_API_BASE_URL=<API Gateway URL>`.

## Architecture

```
main.tsx → App.tsx
  ErrorBoundary              (outside providers: corrupt saved state gets a "Reset app data" screen)
   └ RulesetProvider         audience, channel, selected rulesets, ruleset metadata (GET /api/rules)
      └ UIProvider           progressive reveal, highlights, selected change, toasts
         └ TextProvider      draft, analysis, accept/reject decisions, live scores, chat
            └ AppShell       layout
```

Components read state only through `useRulesets()`, `useText()` and `useUI()`.

### State (`src/context/`)

| Context | Holds |
|---|---|
| `RulesetContext` | `audience`, `channel`, `selectedRulesets` (always in SPEC order), `rulesets` / `audiences` metadata from the API with a fallback to `config/rulesets.ts`. |
| `UIContext` | `revealed` rulesets (FR-5 progressive reveal) with `revealNext` / `revealAll` / `revealNone`, `showHighlights`, `selectedChangeId` (FR-9), toasts. |
| `TextContext` | `text`, `analysis`, `status` (idle/loading/success/error), `isStale`, `runAnalysis` / `cancelAnalysis`, per-change `decisions` (FR-10), derived `currentText`, `openIssues` and `currentScores`, chat (`sendChat` calls `/api/llm/refine`). |

Draft, settings, analysis, decisions and chat persist in `localStorage` under the `uic-editorial:` prefix (`lib/storage.ts`, `lib/usePersistentState.ts`). Everything read back is validated by `lib/sanitize.ts`, so stale or corrupt data is dropped, not trusted.

### Services (`src/services/`)

- `api.ts`: axios clients `backend` (32 s timeout, just above API Gateway's 29 s limit) and `rag` (15 s). Calls `analyze`, `refine`, `getRules`, `getAudiences`, `ragContext`, `ragRetrieve`. Retries 3 times with exponential backoff on network errors, 429 and 5xx (SPEC NFR-3). Supports `AbortSignal` cancellation. Errors are normalised to `ApiError`.
- `mockData.ts`: `mockAnalyze` / `mockRefine` and mock guideline excerpts, matching `types/api.ts`.
- `ws2Adapter.ts`: maps Workstream 2's rule-engine shapes to frontend types: audience/channel ids (`Students` ↔ `students`, `Social Media` ↔ `social_media`), status labels (`Minor Revisions` → `Minor Revisions Needed`), and Python code-point offsets to JavaScript UTF-16 offsets (emoji count as 2 in JS).

### Logic (`src/lib/`)

- `changes.ts`: normalises changes, decides whether a change is applied (`isChangeApplied`: its ruleset is revealed and it was not rejected, or it was explicitly accepted), builds highlight segments and the current text.
- `scoring.ts`: live compliance scores. Mirrors WS2 `scoring_service.py`: deductions high 10 / medium 5 / low 2, at most 3 deductions per rule, brand vs accessibility groups, status classification. `lib/__tests__/scoringParity.test.ts` checks parity against the engine's results on all 24 demo drafts. If the status thresholds change (see MASTER_CHECKLIST notes), change both sides together.
- `readability.ts`: Flesch-Kincaid grade, syllable and sentence counts.
- `sanitize.ts`, `storage.ts`, `usePersistentState.ts`: safe persistence.

### Config and types

- `config/rulesets.ts`: the five rulesets (Brand, Accessibility, Content, Reading Level, Audience Tone) with names, descriptions and `highlight_color`; audiences and channels. `RULESET_ORDER` is the SPEC order used for reveal.
- `types/api.ts`: the request/response types shared with the backend contract.
- `data/demoSamples.json`: compact list of the 24 demo drafts for the sample picker, generated from `data/demo/demo_drafts.json`.

## Components map

| Area | Top-level | Parts |
|---|---|---|
| Layout | `layout/AppShell.tsx` | `Header` (UIC logo + name, `ConnectionStatus` via `useRagHealth`), `Footer`, `HowItWorks`, `ProgressBar`, `ChatDrawer`, `Dialog` + `useFocusTrap`, `Toaster`, `Tip`, `ErrorBoundary` |
| Input | `TextInput.tsx` | `input/SampleMenu` ("Try a sample ▾", featured drafts first), `WordMeter` (word count + limit), `Kbd`, `useAnalyzeGate` |
| Settings | `RulesetPanel.tsx` | `input/SegmentedControl` (audience, channel), `RulesetToggle` (ruleset checkboxes), Analyze button |
| Comparison | `ComparisonView.tsx` | `comparison/RevealBar` (reveal one ruleset at a time / all), `TextPanes` + `PaneFrame` (side-by-side, highlights), `ChangeList`, `ChangeDetail` (popover: reason, guideline excerpt, accept/reject), `ComparisonStates` (empty/loading/error), `useComparisonData` |
| Compliance | `ComplianceDisplay.tsx` | `compliance/ScoreGauge`, `StatTiles`, `IssueList` (grouped by ruleset), `useCountUp` |
| Chat | `ChatInterface.tsx` | `chat/Composer`, `MessageItem`, `Markdown` + `markdownParser` (safe subset, no raw HTML), `EmptyState` (suggested prompts) |
| Export | `ExportButton.tsx` | `export/clipboard` (copy), `pdfReport` (jsPDF report: revised text, scores, issues, changes); plain-text download |

## Design system (summary)

Full brief: [frontend/DESIGN.md](../frontend/DESIGN.md).

- Product name is always "UIC Brand Teammate". Minimal UI: one short sentence per card at most, one primary button per area, details behind disclosure.
- Official UIC logo in `public/brand/` (never recolored or stretched). These are UIC trademarks: confirm with smcs@uic.edu before a public deploy.
- Colors: Expo White canvas, white cards, Navy Pier Blue (`uic-navy`) for headings, primary buttons and focus, Flames Red (`uic-red`) as accent only. Status: Approved `#00966C`, Minor `#B45309`, Major `#D50032`.
- Ruleset highlights use the ruleset color at ~15% alpha plus a 2px underline, always paired with a text label (WCAG 1.4.1).
- Icons from `lucide-react`. Motion 150–200 ms, `prefers-reduced-motion` respected.
- Accessibility (WCAG 2.1 AA): semantic HTML, labelled controls, visible focus, keyboard operable, Esc closes popovers, `aria-live="polite"` for results, contrast ≥ 4.5:1.

## Testing

vitest + Testing Library + jsdom (`src/test/setup.ts`), about 170 tests:

- `components/__tests__/`: each main component, the App, layout, input QA, chat Markdown.
- `context/__tests__/`: providers, persistence and reveal/decision logic.
- `services/__tests__/`: API client (retries, errors, mocks vs live) and `ws2Adapter`.
- `lib/__tests__/`: changes, readability, sanitize, and the scoring parity test against WS2.

Manual checks so far: Chrome. Safari, Firefox and Edge are not yet tested.
