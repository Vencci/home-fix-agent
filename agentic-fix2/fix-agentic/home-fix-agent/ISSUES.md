# Home Fix Agent — Issues & Optimizations

Audit of functional bugs, UX/flow problems, performance, security, and cosmetic issues.

---

## Confirmed Bugs (user-reported)

### Bug 1 — Sessions not chronologically sorted
**File:** `src/storage/store.py:35`
`sorted(sessions_dir().iterdir(), reverse=True)` sorts by **directory name** (random hex), not by `created_at` timestamp. Result is effectively random order.

### Bug 2 — No direct link on product titles
**File:** `static/index.html:1161`
`pcard-title` renders the product title as plain escaped text. The product URL is buried under "Details ▾". The title should be an `<a href>` when `p.url` exists.

### Bug 3 — Rich cards duplicated on every refinement
**File:** `static/index.html:992–1009`
`renderRichContent()` is called from both `renderSessionMessages` and `renderNewMessages`. On every user chat/refinement, it appends the difficulty card, spec card, product grid, and cost card again without clearing the previous ones. After N refinements there are N+1 copies of each card. This is also why the response flow feels cluttered — new cards pile below old ones.

---

## New Bugs Found

### Bug 4 — Orphaned session directories on every web upload
**File:** `src/web.py:57–67`, `src/pipeline.py:20`
`web.py` creates a `Session()` with `sid` and stores the photo under `sessions/{sid}/photo`. Then `start_session(stored, description)` in `pipeline.py` creates a **second** `Session()` with a brand-new random ID. The result is saved to `sessions/{new_id}/result.json` while the photo lives in `sessions/{sid}/`. Every web upload creates an orphaned directory containing only the photo, with no corresponding `result.json`.

### Bug 5 — Sidebar status badge has no CSS styling
**File:** `static/index.html:1339`
The sidebar renders `class="sstage sstage-${s.status}"` using `SessionStatus` values: `"active"`, `"completed"`, `"abandoned"`. The stylesheet only defines `.sstage-results`, `.sstage-done`, `.sstage-clarifying`, `.sstage-error`, `.sstage-analyzing`, `.sstage-searching`. None of the three status values match, so all session badges render completely unstyled.

### Bug 6 — Vision analyst default prompt missing 5 schema fields
**File:** `src/agents/vision_analyst.py:25`
The hardcoded `_DEFAULT_SYSTEM` prompt defines the JSON return schema but omits: `fix_summary`, `diy_or_hire`, `hire_reason`, `hire_price_min_cents`, `hire_price_max_cents`. When no custom `prompts/vision_analyst.md` override is present, the LLM never returns these fields and all silently default to empty. The fix plan, DIY/hire recommendation, and labor cost estimate in the UI will never render.

### Bug 7 — `load_result` creates directories as a side effect
**File:** `src/storage/store.py:25`
`load_result` calls `_session_dir(session_id)` which runs `d.mkdir(parents=True, exist_ok=True)` before checking whether `result.json` exists. Every request with a nonexistent or malformed session ID silently creates an empty directory on disk.

### Bug 8 — `formatMarkdown` produces invalid HTML for lists
**File:** `static/index.html:1348–1354`
The list-wrap regex runs before the `\n→<br>` substitution. After wrapping, the `\n` between `<li>` items becomes `<br>` inside `<ul>` — invalid HTML. The `<ul>` wrap regex is also non-global with dotAll, meaning mixed content (text + list) can be incorrectly wrapped.

### Bug 9 — "Apply Changes" spec edit gives no feedback on no-op
**File:** `static/index.html:1111–1128`
If the user opens the spec card, changes nothing, and clicks "Apply Changes", `edits.length === 0` causes a silent early return with no user feedback. The user has no way to tell whether the button worked or not.

### Bug 10 — LLM price-to-cents fix threshold is wrong
**File:** `src/agents/product_searcher.py:82–83`
```python
if pr.price_cents > 0 and pr.price_cents < 500:
    pr.price_cents *= 100
```
This treats any value under 500 (i.e., under $5.00) as a dollar amount and multiplies by 100, corrupting the price of legitimate sub-$5 items (screws, small bulbs, basic hardware).

---

## UX / Response Flow Issues

### UX 1 — Redundant system status noise in the chat
**File:** `src/pipeline.py:54,99`
"Analyzing your photo..." and "Searching for: `{query}`" are injected as `SYSTEM` messages and rendered as gray status lines in the conversation. They add no value to the user beyond the analysis result and product cards that follow immediately after.

### UX 2 — Clarification message repeats on every refinement
**File:** `src/pipeline.py:85–91`
`_run_spec_extraction` always appends "I'm searching with best-effort specs. To improve results, you can answer: …" whenever there are low-confidence fields — including on the 2nd and 3rd refinement rounds after the user has already answered those questions.

### UX 3 — "Found N products" text bubble is redundant with the product cards
**File:** `src/pipeline.py:116–120`
The assistant says "Found N products. You can select one to order, or tell me if you'd like something different." as a text bubble immediately before the products grid renders. The instruction is self-evident from the UI and duplicates the signal.

### UX 4 — Difficulty and spec cards re-render unchanged on refinements
**File:** `static/index.html:993–998`
`renderRichContent` always appends the difficulty card and spec card on every render, including refinements where only the products and cost estimate changed. The difficulty assessment never changes and should appear only once; the spec card should replace the previous one, not duplicate it.

### UX 5 — Input bar shows wrong state for old sessions missing a `stage` field
Old sessions serialized before the `stage` field existed deserialize with the `PipelineStage.UPLOAD` default. Loading them from the sidebar shows the input bar with a generic "Type a message..." placeholder even if the session is complete, allowing the user to attempt a refinement on a stale session.

---

## Performance Issues

### Perf 1 — YAML config files read from disk on every ranking call
**File:** `src/agents/product_ranker.py:31`
`load_ranking()` opens and parses `ranking.yaml` on every call to `rank()`. Should be cached at module level.

### Perf 2 — `list_sessions` fully deserializes every `result.json`
**File:** `src/storage/store.py:41`
Loads the entire `PipelineResult` (messages, products, specs, history) via Pydantic just to extract 5 display fields. Should parse the JSON dict directly without full model validation.

### Perf 3 — Photo base64-encoded twice per request
**File:** `src/utils/llm.py:22`
`_encode_image` reads and base64-encodes the full photo file in both `vision_analyst.analyze` and `spec_extractor.extract`. For a 20 MB image this allocates ~53 MB per request. The encoded bytes should be passed through rather than re-read from disk.

---

## Security Issues

### Sec 1 — Path traversal in `/session/{session_id}` endpoints
**File:** `src/web.py:107,115`
`session_id` from the URL path is passed directly to `_session_dir()`, which constructs `sessions_dir() / session_id`. A crafted ID such as `../../etc/passwd` could escape the sessions directory. Session IDs should be validated against a strict format (e.g., `^[a-f0-9]{12}$`) before use.

### Sec 2 — `appendPhoto` uses `innerHTML` with unsanitized src
**File:** `static/index.html:1022`
```js
div.innerHTML = `<img src="${src}" alt="Uploaded photo">`;
```
If `src` ever contains a quote character, this is an XSS vector. Should use `createElement` + `setAttribute` instead.

---

## Minor / Cosmetic

### Minor 1 — Sidebar date shows no time component
`new Date(s.created_at).toLocaleDateString()` — two sessions created on the same day are indistinguishable in the sidebar.

### Minor 2 — `URL.createObjectURL` blob URL never revoked
**File:** `static/index.html:861`
Blob URLs created for the photo preview accumulate in memory across sessions and are never cleaned up with `URL.revokeObjectURL()`.

### Minor 3 — Rate limit state is in-memory only
**File:** `src/web.py:26–27`
`_request_log` resets on every server restart and is not shared across multiple worker processes. The 2-req/min limit is ineffective in production deployments.

### Minor 4 — `picks` field in `list_sessions` response is never shown in the UI
**File:** `src/storage/store.py:47`
`"picks": len(r.products)` is computed and returned but not used anywhere in the frontend.

### Minor 5 — "Buy Now" button label implies a real purchase
The order flow is a mock/demo but the button says "Buy Now", which may mislead users. A label like "Order (Demo)" or "Select" sets clearer expectations.

---

## Summary

| Category | Count |
|---|---|
| Confirmed bugs (user-reported) | 3 |
| New bugs | 7 |
| UX / flow issues | 5 |
| Performance | 3 |
| Security | 2 |
| Minor / cosmetic | 5 |
| **Total** | **25** |
