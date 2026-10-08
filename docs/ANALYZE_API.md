# Analyze API (integrated backend, Task I.3)

Base URL: `https://rtjsllveri.execute-api.us-east-1.amazonaws.com` (Lambda `uic-editorial-rag-api`, app `backend/api/main.py`, interactive docs at `/docs`).
Request/response shapes are binding: **`frontend/src/types/api.ts`** (`AnalyzeRequest/AnalyzeResponse`, `RefineRequest/RefineResponse`).

| Endpoint | Purpose |
|---|---|
| `POST /api/analyze` | Rules (WS2) + guideline retrieval (WS1) in parallel, then Bedrock rewrite into ruleset-tagged `changes` |
| `POST /api/llm/refine` | Chat: answers questions (with `> quote` + `Source: <url>`) or re-runs the analysis on `original` with the user's instruction (returns `analysis`) |
| `GET /api/rules`, `/api/rules/{id}`, `POST /api/rules/check`, `GET /api/audiences` | WS2 rule engine (unchanged) |
| `/api/rag/*` | WS1 retrieval (unchanged) |

- `audience`/`channel` accept Title case (`Students`, `Social Media`) or lowercase (`students`, `social_media`); responses use Title case. Omitted/empty `rulesets` = all five.
- All offsets (`issues[].start/end`, `changes[].original_start/end`) are **JS UTF-16** indexes into `original`. Changes never overlap; `rewritten` = all changes applied.
- `scores.status` uses the display form: `Approved` / `Minor Revisions Needed` / `Major Revisions Needed`.
- Errors: 422 invalid input (blank / >5,000 words / unknown audience, channel, ruleset); 503 rule engine or RAG unavailable. Bedrock failures never fail the request.

```bash
curl -X POST $URL/api/analyze -H 'content-type: application/json' \
  -d '{"text":"Hey guys! Visit the University of Illinois at Chicago.","audience":"Students","channel":"Email","rulesets":["brand","accessibility","content","reading_level","audience_tone"]}'
curl -X POST $URL/api/llm/refine -H 'content-type: application/json' \
  -d '{"message":"Make it more formal","original":"...","current_text":"...","audience":"Students","channel":"Email","rulesets":["brand"],"history":[]}'
```

## Model selection, retries, fallback (`backend/services/rewrite_service.py`)
- Models from `UIC_MODEL_FAST` / `UIC_MODEL_QUALITY` env (set at deploy) > SSM `/uic-editorial/model_fast|model_quality` > defaults: fast = `us.anthropic.claude-haiku-4-5-20251001-v1:0`, quality = `us.anthropic.claude-sonnet-5`.
- Adaptive: fast model when the draft has < 300 words **and** < 8 issues; quality otherwise. Chat intent classification always uses the fast model.
- Converse API with forced tool `submit_edits` → `{edits:[{ruleset, original, replacement, explanation, issue_ids}], skipped_issue_ids, summary}`. Each `original` is located in the draft (exact, then whitespace/quote-normalized, then case-insensitive; prefers the occurrence overlapping a referenced issue); not-found/overlapping edits are dropped. Literal rule suggestions the model neither fixed nor skipped are gap-filled deterministically.
- Up to 3 attempts, exponential backoff + jitter on throttling/5xx/timeouts, within a 25 s request budget; a failing quality model switches to the fast model.
- If Bedrock fails entirely: deterministic changes from WS2 issues whose suggestion is literal replacement text; `model_used = "rules-fallback"`.
- Logs (CloudWatch `/uic-editorial/backend`): events `rewrite_model_selected`, `llm_converse`, `llm_converse_error`, `rewrite_done`, `analyze_done`, `refine_done`.

## Replacing with Workstream 3
`rewrite_service.py` is an interim stand-in. WS3's `llm_service.py` can take over by providing an object with
`rewrite(text, issues, guidelines, audience, channel, rulesets, instruction=None, deadline=None) -> RewriteResult`
(changes in **code-point** offsets; the orchestrator converts to UTF-16) plus `converse_tool(...)`/`model_fast` for refine,
and returning it from `rewrite_service.get_rewrite_service()` (or passing `rewriter=` to `orchestrator.analyze/refine`).
