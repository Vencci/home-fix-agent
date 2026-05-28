# Spec-Driven Development Doc

**Project:** Agentic Home Project Assistant

| Field | Value |
|---|---|
| Status | Draft v1.1 |
| Owner | User / Product + Engineering |
| Last Updated | 2026-04-28 |

---

## 1. Problem Statement

Homeowners frequently encounter small maintenance issues — a broken light bulb, a leaky faucet washer, a cracked outlet cover — but struggle to identify the exact replacement part, find it online, and order it. The process requires domain knowledge (bulb base type, wattage, color temperature) that most people lack.

Build an agentic system that accepts a photo of a home maintenance issue, analyzes the problem using vision AI, identifies the correct replacement product with precise specifications, searches available products on the market, presents options to the user, and — after explicit human confirmation — places the order.

The system is **human-in-the-loop by design**. It never places an order without the user reviewing and approving the product, price, and quantity.

---

## 2. Goals

1. Accept a user-submitted photo of a home maintenance issue.
2. Analyze the photo to identify the problem and the item that needs replacement.
3. Extract product specifications from the image (e.g., bulb type, wattage, base size, dimensions).
4. Search online retailers for matching replacement products.
5. Present a ranked list of product options with price, rating, and compatibility notes.
6. Allow the user to select a product and confirm the order.
7. Place the order on behalf of the user after explicit confirmation.
8. Store interaction history for repeat purchases and audit.

---

## 3. Non-Goals

1. Do not handle complex renovations requiring professional contractors.
2. Do not provide electrical, plumbing, or structural safety advice.
3. Do not store payment credentials directly — delegate to retailer checkout or payment provider.
4. Do not autonomously place orders without human confirmation.
5. Do not diagnose issues that require physical inspection beyond what a photo can show.
6. Do not provide price prediction or deal-timing advice.

---

## 4. Product Scope

### In Scope (v1)

- Photo-based issue identification for common home items (bulbs, batteries, filters, covers, knobs, fasteners)
- Specification extraction from photos (type, size, wattage, color, model number)
- Product search via retailer APIs (Amazon Product Advertising API or similar)
- Product comparison and ranking
- Human confirmation gate before ordering
- Order placement via retailer API
- Conversation history and order history storage

### Out of Scope (v1)

- Video-based analysis
- Multi-step repair instructions or tutorials
- Professional contractor matching
- Smart home device integration
- Price tracking and alerts
- Multi-item project planning (e.g., "remodel my bathroom")
- International shipping or multi-currency support

---

## 5. Target Users

1. **Homeowner** — non-technical person who wants to fix a simple issue without researching part numbers.
2. **Renter** — needs to replace a broken item quickly and correctly to avoid lease issues.
3. **Property manager** — handles multiple units and wants fast, repeatable ordering for common parts.

---

## 6. Operating Principle

The system should behave like a knowledgeable hardware store employee:

- **One agent looks at the photo** and figures out what's wrong.
- **One agent identifies the exact specs** of the item that needs replacement.
- **One agent searches the market** for matching products.
- **One agent ranks and presents options** with clear reasoning.
- **One agent handles the order** only after the human says "yes."

No single agent should both recommend a product and place the order without a human review step in between.

---

## 7. High-Level Workflow

1. User submits a photo and optional text description of the issue.
2. Vision agent analyzes the photo: identifies the item, the problem, and visible specs.
3. Spec extraction agent determines the full product specification (type, size, wattage, base, color temp, etc.).
4. If specs are ambiguous, the system asks the user clarifying questions.
5. Product search agent queries retailer APIs with extracted specs.
6. Ranking agent scores and filters results by relevance, price, rating, and availability.
7. System presents top 3–5 product options to the user with comparison details.
8. User selects a product (or requests more options / refines criteria).
9. System shows order summary: product, quantity, price, shipping, and estimated delivery.
10. User explicitly confirms the order.
11. Order agent places the order via retailer API.
12. System stores the interaction, specs, and order record for history and replay.

---

## 8. Functional Requirements

### FR-1: Photo Intake

The system shall accept photos in JPEG, PNG, and HEIC formats up to 20 MB. It shall accept an optional text description alongside the photo.

**Inputs:** Image file, optional text description.
**Outputs:** Stored image reference, session ID.

### FR-2: Issue Identification

The system shall analyze the photo using a vision model to determine:
- What item is shown (e.g., light bulb, faucet handle, outlet cover)
- What is wrong with it (e.g., broken, burned out, cracked, missing)
- Visible brand, model, or part numbers if readable

**Outputs:** Structured issue record with item category, problem type, and any visible identifiers.

### FR-3: Specification Extraction

The system shall infer or extract product specifications from the photo and context:
- For bulbs: base type (E26, E12, GU10), wattage, color temperature, shape (A19, BR30, PAR38), dimmable
- For batteries: size (AA, AAA, CR2032, 9V), chemistry
- For filters: dimensions, MERV rating, brand compatibility
- For hardware: size, thread type, material, finish

If specifications cannot be fully determined from the photo, the system shall ask the user targeted clarifying questions.

**Outputs:** Structured spec record with all identified parameters and confidence levels.

### FR-4: Product Search

The system shall search one or more retailer APIs using the extracted specifications. It shall return products that match the required specs.

**Inputs:** Structured spec record.
**Outputs:** Raw product list with title, price, rating, availability, URL, and images.

### FR-5: Product Ranking and Presentation

The system shall rank search results by:
- Specification match accuracy
- Customer rating and review count
- Price
- Availability and shipping speed
- Brand reputation

It shall present the top 3–5 options with a brief explanation of why each was selected.

### FR-6: User Selection and Clarification

The system shall allow the user to:
- Select a product from the presented options
- Ask for more options
- Refine search criteria (e.g., "I want LED, not incandescent")
- Ask questions about a specific product

### FR-7: Order Confirmation Gate

Before placing any order, the system shall display:
- Product name and image
- Quantity
- Unit price and total price
- Shipping cost and estimated delivery date
- Retailer name

The user must explicitly confirm (e.g., "Yes, place the order") before the system proceeds.

### FR-8: Order Placement

The system shall place the order via the retailer API using the user's pre-configured account/payment method. It shall return an order confirmation with order ID and tracking information when available.

### FR-9: Interaction History

The system shall store:
- All photos submitted
- Issue analysis results
- Spec extractions
- Search results
- User selections
- Order confirmations
- Timestamps and session IDs

This enables repeat purchases, debugging, and audit.

### FR-10: Error Handling and Fallback

- If the photo is unclear: ask the user for a better photo or additional angles.
- If specs cannot be determined: present what is known and ask the user to fill gaps.
- If no products match: broaden search and explain what was relaxed.
- If order placement fails: report the error and suggest manual purchase with a direct link.

---

## 9. Quality Requirements

### QR-1: Accuracy

Specification extraction must be correct for the primary identifying parameters (e.g., bulb base type, battery size) at least 90% of the time on clear photos.

### QR-2: Latency

Photo analysis through product presentation should complete within 15 seconds for a typical request.

### QR-3: Human-in-the-Loop Safety

No order shall be placed without explicit user confirmation. The confirmation step must be a separate, unambiguous interaction — not a default or auto-proceed.

### QR-4: Auditability

All intermediate outputs (photo analysis, specs, search results, user confirmations) shall be stored with session IDs and timestamps.

### QR-5: Graceful Degradation

If a retailer API is unavailable, the system shall try alternative sources or provide a manual search link. Partial results are better than no results.

### QR-6: Cost Control

Vision and LLM calls shall only run after basic input validation. Redundant API calls for the same specs within a session shall be cached.

### QR-7: Privacy

User photos and order data shall be stored securely. Photos shall not be shared with third parties beyond the vision model provider. Payment credentials shall never be stored by the system — delegate to the retailer.

---

## 10. Agent Architecture

### Agent A: Vision Analyst

**Responsibility:** Analyze the submitted photo to identify the item and the problem.

**Inputs:** Photo (image bytes), optional user text description.

**Outputs:** Structured issue record — item category, problem type, visible identifiers, confidence score.

### Agent B: Spec Extractor

**Responsibility:** Determine the full replacement product specification from the photo analysis and any visible markings.

**Inputs:** Issue record from Agent A, original photo for re-inspection if needed.

**Outputs:** Structured spec record with all relevant parameters (type, size, wattage, base, color, material, etc.) and confidence per field.

**Clarification behavior:** If any critical spec has confidence below threshold, generate a targeted question for the user.

### Agent C: Product Searcher

**Responsibility:** Query retailer APIs with the extracted specs to find matching products.

**Inputs:** Spec record, user preferences (price range, brand preference, Prime-eligible).

**Outputs:** Raw product list with metadata (title, price, rating, review count, availability, URL, image URL, ASIN/SKU).

### Agent D: Product Ranker

**Responsibility:** Score and rank search results, then present the top options with reasoning.

**Inputs:** Raw product list, spec record (for match scoring).

**Outputs:** Ranked product list (top 3–5) with match score, price, rating, and a one-sentence explanation per product.

### Agent E: Order Manager

**Responsibility:** Handle the confirmation flow and place the order.

**Inputs:** User-selected product, quantity, shipping preference.

**Outputs:** Order confirmation gate (summary for user review), then order confirmation (order ID, tracking).

**Rule:** This agent must never proceed to order placement without receiving an explicit "confirm" signal from the user.

---

## 11. Data Model

### 11.1 Session

| Field | Type |
|---|---|
| session_id | string |
| user_id | string |
| created_at | datetime |
| status | enum: active, completed, abandoned |
| photo_ids | string[] |

### 11.2 Photo

| Field | Type |
|---|---|
| photo_id | string |
| session_id | string |
| file_path | string |
| format | string (jpeg, png, heic) |
| size_bytes | int |
| uploaded_at | datetime |

### 11.3 IssueAnalysis

| Field | Type |
|---|---|
| analysis_id | string |
| session_id | string |
| photo_id | string |
| item_category | string (bulb, battery, filter, hardware, faucet, cover, other) |
| problem_type | string (broken, burned_out, cracked, missing, worn, other) |
| visible_brand | string (nullable) |
| visible_model | string (nullable) |
| visible_text | string[] |
| confidence | float 0–1 |
| raw_llm_output | json |

### 11.4 ProductSpec

| Field | Type |
|---|---|
| spec_id | string |
| session_id | string |
| analysis_id | string |
| item_category | string |
| attributes | json (key-value pairs, e.g., {"base_type": "E26", "wattage": 60, "color_temp_k": 2700}) |
| confidence_per_field | json (e.g., {"base_type": 0.95, "wattage": 0.80}) |
| clarification_needed | string[] (fields needing user input) |

### 11.5 ProductResult

| Field | Type |
|---|---|
| result_id | string |
| session_id | string |
| spec_id | string |
| retailer | string |
| title | string |
| price_cents | int |
| currency | string |
| rating | float |
| review_count | int |
| availability | string (in_stock, limited, out_of_stock) |
| url | string |
| image_url | string |
| asin_or_sku | string |
| match_score | float 0–1 |
| rank | int |

### 11.6 OrderRecord

| Field | Type |
|---|---|
| order_id | string |
| session_id | string |
| result_id | string |
| user_id | string |
| product_title | string |
| quantity | int |
| unit_price_cents | int |
| total_price_cents | int |
| shipping_cost_cents | int |
| retailer_order_id | string |
| status | enum: pending_confirmation, confirmed, placed, shipped, delivered, failed |
| confirmed_at | datetime (nullable) |
| placed_at | datetime (nullable) |

### 11.7 PipelineStage (v1.1)

Enum tracking the current position in the interactive pipeline:

| Value | Description |
|---|---|
| upload | Photo submitted, pipeline not yet started |
| analyzing | Vision analysis in progress |
| clarifying | Blocking on user clarification — spec extractor has questions |
| searching | Product search in progress |
| results | Products presented, user may select or refine |
| refining | Re-searching with user feedback |
| ordering | Order confirmation in progress |
| done | Order placed or session complete |
| error | Pipeline failed at some stage |

### 11.8 ChatMessage (v1.1)

| Field | Type |
|---|---|
| role | enum: system, user, assistant |
| content | string |
| timestamp | datetime |
| stage | string (nullable) — pipeline stage when message was created |

### 11.9 PipelineResult (v1.1)

The top-level session artifact, extended to support the interactive conversation flow:

| Field | Type |
|---|---|
| session | Session |
| stage | PipelineStage (default: upload) |
| messages | ChatMessage[] (default: []) |
| analysis | IssueAnalysis (nullable) |
| spec | ProductSpec (nullable) |
| products | ProductResult[] (default: []) |
| order | OrderRecord (nullable) |
| error | string (nullable) |

The `messages` list provides a complete conversation transcript for the session. The `stage` field determines what user actions are valid: during `clarifying`, only clarification answers advance the pipeline; during `results`, the user may select a product or send refinement feedback.

---

## 12. Ordering Flow (State Machine)

```
UPLOAD
    → ANALYZING
        → CLARIFYING (blocking — user must answer before search proceeds)
            → user answers → re-run Spec Extractor with context
                → CLARIFYING (if still uncertain)
                → SEARCHING (if specs resolved)
        → SEARCHING (if no clarification needed)
            → RESULTS
                → user selects product → ORDERING → DONE
                → user sends refinement → REFINING → RESULTS
        → ERROR (analysis failed — ask for better photo)
```

Key invariants:
- The `CLARIFYING` stage is **blocking**: the pipeline does not proceed to product search until the user answers the spec extractor's questions or the questions are resolved. This prevents the common failure mode where an uncertain spec leads to confidently wrong product recommendations.
- The transition from `RESULTS` to `DONE` (via `ORDERING`) requires an explicit user confirmation. The system must not auto-advance this transition.
- From `RESULTS`, the user may send free-text refinement feedback (e.g., "I need dimmable", "show me cheaper options"). This appends the feedback to the search query and re-runs the search/rank cycle, returning to `RESULTS` with updated products.

---

## 13. Suggested Tech Stack

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python | Strong ecosystem for vision/LLM/API work |
| Vision/LLM | OpenAI GPT-4o (vision) or Claude Sonnet | Multimodal, structured JSON output |
| Product Search | SerpAPI for Google Shopping, mock fixtures, LLM-generated fallback | Three-tier strategy for availability |
| Pipeline | Incremental Python pipeline (`pipeline.py`) with stage-based advancement | Supports blocking clarification and refinement loops |
| Storage | JSON files on disk (per-session directory) | Zero-config, human-readable, easy to debug |
| Image Storage | Local filesystem (MVP) → S3 (production) | Simple start |
| UI | Chat-driven web interface (FastAPI + single HTML file) and CLI | Both interfaces share the same incremental pipeline |
| API Framework | FastAPI | Lightweight, async-friendly |
| Deployment | Docker on Fly.io | Simple container deployment with encrypted secrets |

---

## 14. Prompting / Structured Output Specs

All LLM agents must return strict JSON. Prompts must include the expected schema.

### Vision Analyst Output Schema

```json
{
  "item_category": "string",
  "problem_type": "string",
  "visible_brand": "string | null",
  "visible_model": "string | null",
  "visible_text": ["string"],
  "description": "string",
  "confidence": 0.0
}
```

### Spec Extractor Output Schema

```json
{
  "item_category": "string",
  "attributes": {
    "base_type": "string",
    "wattage": 0,
    "color_temperature_k": 0,
    "shape": "string",
    "dimmable": true,
    "finish": "string"
  },
  "confidence_per_field": {
    "base_type": 0.0,
    "wattage": 0.0
  },
  "clarification_questions": ["string"],
  "search_query": "string"
}
```

### Product Ranker Output Schema

```json
{
  "ranked_products": [
    {
      "result_id": "string",
      "match_score": 0.0,
      "recommendation_reason": "string",
      "warnings": ["string"]
    }
  ]
}
```

---

## 15. Example Scenarios

### Scenario 1: Broken Light Bulb

1. User uploads photo of a burned-out bulb still in the socket.
2. Vision Analyst: "item_category: bulb, problem_type: burned_out, visible_text: ['60W', 'E26']"
3. Spec Extractor: "base_type: E26, wattage: 60, shape: A19, color_temp: 2700K (inferred from warm appearance), dimmable: unknown"
4. System asks: "Is this bulb on a dimmer switch?"
5. User: "No"
6. Product Search returns 12 results for "E26 60W A19 LED bulb 2700K"
7. Ranker presents top 3: best match, best value, best rated.
8. User selects option 2.
9. System shows: "Philips LED A19 60W 2700K, $3.97, arrives Thursday. Place order?"
10. User: "Yes"
11. Order placed. Confirmation shown.

### Scenario 2: Unknown Battery Size

1. User uploads photo of a remote control with battery compartment open.
2. Vision Analyst: "item_category: battery, problem_type: missing, visible_text: ['CR2032']"
3. Spec Extractor: "size: CR2032, chemistry: lithium, voltage: 3V"
4. No clarification needed — specs are clear from visible text.
5. Search, rank, confirm, order.

### Scenario 3: Ambiguous Photo

1. User uploads a blurry photo of a ceiling fixture.
2. Vision Analyst: "item_category: bulb, problem_type: burned_out, confidence: 0.4"
3. System: "I can see this is a ceiling light, but the photo is too blurry to read the bulb specs. Can you take a closer photo of the bulb itself, or tell me the bulb type?"
4. User provides a clearer photo or types "it's a GU10 spot light."
5. Flow continues with higher confidence.

---

## 16. Recommendation Presentation Template

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  🔧 Home Fix Assistant — Product Options
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Issue: Burned-out light bulb (E26, 60W, 2700K, A19)

Option 1 ⭐ Best Match
  Philips LED A19 60W Equivalent 2700K
  $3.97 | ⭐ 4.7 (12,340 reviews) | In Stock
  ✅ Exact spec match | Ships tomorrow
  Why: Matches all specs, top-rated, lowest price.

Option 2 💰 Best Value
  Amazon Basics A19 LED 60W 2700K (4-pack)
  $8.49 ($2.12/bulb) | ⭐ 4.5 (8,200 reviews) | In Stock
  ✅ Exact spec match | Multi-pack value
  Why: Same specs, better per-unit price if you need spares.

Option 3 🏆 Highest Rated
  Cree A19 LED 60W 2700K Dimmable
  $5.49 | ⭐ 4.8 (6,100 reviews) | In Stock
  ✅ Exact spec match | Dimmable (bonus feature)
  Why: Highest rated, dimmable for future flexibility.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Reply with 1, 2, or 3 to select, or type
"more options" / "I want [criteria]" to refine.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 17. MVP Implementation Package

### 17.1 MVP Goal

Build a home project assistant with both CLI and web interfaces that:

1. Accepts a photo of a broken/missing home item.
2. Analyzes the photo to identify the item and problem.
3. Extracts replacement product specifications.
4. **Blocks and asks the user clarifying questions** when spec confidence is low.
5. Searches for matching products online.
6. Presents ranked options to the user.
7. **Allows the user to refine results** through conversational follow-up.
8. Confirms with the user before placing an order.
9. Stores all interaction artifacts — including the conversation transcript — for replay and debugging.

The system supports an **interactive conversation flow** where the user and system exchange messages throughout the pipeline, rather than a single fire-and-forget request.

### 17.2 MVP User Story

As a homeowner, I want to take a photo of a broken item, run a command, and get a list of replacement products I can buy — so that I don't have to figure out part numbers myself.

### 17.3 MVP Scope

**Included:**
- Photo input via CLI (file path) and web UI (drag-and-drop upload)
- Vision analysis via OpenAI GPT-4o or equivalent
- Spec extraction with **blocking clarification loop** — pipeline pauses until user answers
- Product search via SerpAPI (Google Shopping), mock fixtures, or LLM-generated fallback
- Ranked product presentation in terminal and chat-driven web UI
- **Conversational refinement** — user can send follow-up messages to adjust search criteria
- Order confirmation prompt (y/n in CLI, confirm dialog in web UI)
- Order placement via API (or mock in MVP)
- JSON file storage for sessions, with full conversation transcript
- Replay: view past sessions and their outputs (CLI and web sidebar)
- Chat-driven web interface with progressive disclosure of pipeline stages
- Docker deployment on Fly.io

**Excluded:**
- Real payment processing (mock order placement in MVP)
- Multi-user accounts
- Image preprocessing or enhancement
- Multi-language support

### 17.4 MVP Success Criteria

The MVP is successful if:
- It correctly identifies the item category in 8/10 test photos.
- It extracts the primary spec (e.g., bulb base type) correctly in 8/10 clear photos.
- It returns at least 3 relevant products for each successful spec extraction.
- The confirmation gate blocks every order until the user types "yes."
- A past session can be replayed and inspected.

### 17.5 MVP Architecture

```
User (CLI or Web Chat UI)
  │
  ├─ photo + optional description
  │
  ▼
Pipeline Runner (pipeline.py) — incremental, stage-based
  │
  ├─ 1. Photo Intake ──────────► validate + store image
  ├─ 2. Vision Analyst ────────► LLM vision call → IssueAnalysis
  ├─ 3. Spec Extractor ────────► LLM call → ProductSpec
  │     └─ BLOCKING: if clarification_questions → pause at CLARIFYING stage
  │                  user answers via /chat or CLI prompt
  │                  re-run Spec Extractor with user context
  ├─ 4. Product Searcher ──────► retailer API → ProductResult[]
  ├─ 5. Product Ranker ────────► heuristic scoring → ranked list
  ├─ 6. Present Results ───────► chat message + product cards (web) or terminal (CLI)
  │     └─ LOOP: user may send refinement feedback → re-search → re-rank
  ├─ 7. User Selection ────────► product card Buy button (web) or stdin (CLI)
  ├─ 8. Confirmation Gate ─────► browser confirm() dialog or "yes" in terminal
  ├─ 9. Order Placement ───────► retailer API (or mock)
  └─ 10. Save Session ─────────► JSON files with full conversation transcript

Web API Endpoints:
  POST /analyze  — upload photo, start session, run through analysis + spec extraction
  POST /chat     — send message to existing session (clarification answer or refinement)
  POST /order    — place order for selected product
  GET  /session/{id} — load full session state for replay
  GET  /history  — list past sessions
```

**Decision:** The pipeline is incremental rather than monolithic. Each stage produces a `PipelineResult` with a `stage` field and a `messages` list. The web UI and CLI both call the same `pipeline.py` functions (`start_session` and `advance`), ensuring consistent behavior across interfaces.

---

## 18. MVP Module Specifications

### Module A: Photo Intake

**Purpose:** Validate and store the user's photo.

**Inputs:** File path from CLI argument.

**Outputs:** Photo record (photo_id, file_path, format, size).

**Acceptance Criteria:**
- Rejects files that are not JPEG/PNG/HEIC.
- Rejects files over 20 MB.
- Copies file to session storage directory.

**Failure Modes:**
- File not found → clear error message.
- Unsupported format → list supported formats.
- File too large → show size limit.

### Module B: Vision Analyst

**Purpose:** Analyze the photo to identify the item and problem.

**Inputs:** Photo file path, optional user description.

**Outputs:** IssueAnalysis record (item_category, problem_type, visible identifiers, confidence).

**Acceptance Criteria:**
- Returns structured JSON matching the IssueAnalysis schema.
- Confidence score reflects actual certainty (blurry photo → low confidence).
- Does not hallucinate text that isn't visible in the photo.

**Prompt Contract:**
- Must describe what it sees, not what it assumes.
- Must flag when the image is unclear.
- Must not recommend products (that's a later agent's job).

### Module C: Spec Extractor

**Purpose:** Determine full replacement product specifications.

**Inputs:** IssueAnalysis record, original photo (for re-inspection).

**Outputs:** ProductSpec record with attributes, confidence per field, and clarification questions.

**Acceptance Criteria:**
- Extracts all critical specs for the item category.
- Generates a search query string suitable for retailer APIs.
- Asks clarification questions when confidence is below 0.7 on a critical field.

**Clarification Behavior:**
- The pipeline **blocks** at the `CLARIFYING` stage. Product search does not proceed until clarification is resolved.
- In the web UI, the chat input bar prompts "Answer the questions above..." and the user's response is sent via the `/chat` endpoint.
- In the CLI, the system prints the questions and waits for terminal input.
- The Spec Extractor re-runs with the user's answer appended as `extra_context`.
- If the re-run still produces clarification questions, the pipeline remains at `CLARIFYING`.
- If the re-run resolves all questions, the pipeline advances to `SEARCHING`.

### Module D: Product Searcher

**Purpose:** Query retailer APIs for matching products.

**Inputs:** ProductSpec (specifically the search_query and key attributes).

**Outputs:** List of ProductResult records.

**Acceptance Criteria:**
- Returns at least 3 results when products exist.
- Handles API rate limits and errors gracefully.
- Caches results within a session to avoid redundant calls.

**MVP Implementation:** Use SerpAPI Google Shopping endpoint, or a mock JSON file for offline testing.

### Module E: Product Ranker

**Purpose:** Score and rank search results by relevance.

**Inputs:** ProductResult list, ProductSpec (for match scoring).

**Outputs:** Ranked list with match_score and recommendation_reason per product.

**Scoring Factors:**
- Spec match (does the product match extracted specs?) — weight 0.40
- Rating (customer rating normalized) — weight 0.20
- Price (lower is better, normalized) — weight 0.20
- Availability (in-stock preferred) — weight 0.10
- Review count (more reviews = more trustworthy) — weight 0.10

**Acceptance Criteria:**
- Ranking is deterministic given the same inputs.
- Top result has the highest spec match unless significantly worse on other factors.

### Module F: Order Manager

**Purpose:** Handle selection, confirmation, and order placement.

**Inputs:** Ranked product list, user selection.

**Outputs:** Order confirmation summary, then OrderRecord after placement.

**Acceptance Criteria:**
- Displays full order summary before asking for confirmation.
- Only proceeds on explicit "yes" / "y" input.
- Any other input (including empty) is treated as "no."
- Stores OrderRecord regardless of outcome (confirmed or cancelled).

---

## 19. MVP Data Contracts

### Session Record

```json
{
  "session_id": "sess_20260419_001",
  "user_id": "default_user",
  "created_at": "2026-04-19T08:30:00Z",
  "status": "completed",
  "photo_path": "data/sessions/sess_20260419_001/photo.jpg"
}
```

### Issue Analysis Output

```json
{
  "analysis_id": "ana_001",
  "session_id": "sess_20260419_001",
  "item_category": "bulb",
  "problem_type": "burned_out",
  "visible_brand": "Philips",
  "visible_model": null,
  "visible_text": ["60W", "E26", "2700K"],
  "description": "A burned-out A19 light bulb in a standard ceiling fixture. The base is E26 screw type. Text on the bulb reads 60W and 2700K.",
  "confidence": 0.92
}
```

### Product Spec Output

```json
{
  "spec_id": "spec_001",
  "session_id": "sess_20260419_001",
  "item_category": "bulb",
  "attributes": {
    "base_type": "E26",
    "wattage_equivalent": 60,
    "color_temperature_k": 2700,
    "shape": "A19",
    "technology": "LED",
    "dimmable": false
  },
  "confidence_per_field": {
    "base_type": 0.95,
    "wattage_equivalent": 0.90,
    "color_temperature_k": 0.85,
    "shape": 0.80,
    "technology": 0.70,
    "dimmable": 0.50
  },
  "clarification_questions": ["Is this bulb on a dimmer switch?"],
  "search_query": "E26 60W equivalent A19 LED bulb 2700K"
}
```

### Order Record

```json
{
  "order_id": "ord_001",
  "session_id": "sess_20260419_001",
  "result_id": "res_003",
  "product_title": "Philips LED A19 60W Equivalent Soft White 2700K",
  "quantity": 1,
  "unit_price_cents": 397,
  "total_price_cents": 397,
  "shipping_cost_cents": 0,
  "retailer_order_id": "114-3941689-8772232",
  "status": "placed",
  "confirmed_at": "2026-04-19T08:32:15Z",
  "placed_at": "2026-04-19T08:32:16Z"
}
```

---

## 20. Suggested Repository Structure

```
home-fix-agent/
  README.md
  pyproject.toml
  .env.example
  Dockerfile
  fly.toml
  configs/
    categories.yaml       # supported item categories and their spec fields
    ranking.yaml          # ranking weights
  src/
    __init__.py
    main.py               # CLI entry point
    pipeline.py           # incremental pipeline engine (start_session, advance)
    web.py                # FastAPI server with /analyze, /chat, /order endpoints
    intake/
      photo.py            # photo validation and storage
    agents/
      vision_analyst.py   # photo analysis via vision LLM
      spec_extractor.py   # spec extraction via LLM
      product_searcher.py # retailer API queries (SerpAPI / mock / LLM fallback)
      product_ranker.py   # scoring and ranking
      order_manager.py    # confirmation and order placement
    models/
      schemas.py          # Pydantic data models (Session, PipelineStage, ChatMessage, PipelineResult, etc.)
    storage/
      store.py            # session save/load (JSON files)
    utils/
      config.py           # config loader
      llm.py              # LLM client wrapper (vision + text, JSON output)
  prompts/
    vision_analyst.md
    spec_extractor.md
  static/
    index.html            # chat-driven web UI (single file, no build step)
  tests/
    unit/
      test_pipeline.py    # 26 tests covering schemas, intake, ranking, orders, pipeline stages
    fixtures/
      sample_photos/
      mock_search_results.json
  data/
    mock_search_results.json  # mock product data for offline testing
    sessions/                 # per-session storage (JSON + photos)
```

---

## 21. Supported Item Categories (MVP)

Each category defines which spec fields are required, optional, and their valid values.

### Bulbs

| Field | Required | Example Values |
|---|---|---|
| base_type | yes | E26, E12, GU10, GU5.3, G9, BA15D |
| wattage_equivalent | yes | 40, 60, 75, 100 |
| color_temperature_k | yes | 2700, 3000, 4000, 5000 |
| shape | yes | A19, A21, BR30, PAR38, MR16, candelabra |
| technology | yes | LED, CFL, incandescent, halogen |
| dimmable | optional | true, false |
| finish | optional | clear, frosted |

### Batteries

| Field | Required | Example Values |
|---|---|---|
| size | yes | AA, AAA, C, D, 9V, CR2032, CR2025, CR123A |
| chemistry | optional | alkaline, lithium, NiMH |
| voltage | optional | 1.5, 3.0, 9.0 |
| quantity | optional | 1, 2, 4, 8 |

### Filters (HVAC / Air)

| Field | Required | Example Values |
|---|---|---|
| length_inches | yes | 16, 20, 24 |
| width_inches | yes | 20, 25 |
| depth_inches | yes | 1, 2, 4 |
| merv_rating | optional | 8, 11, 13 |

### Hardware (Fasteners, Knobs, Covers)

| Field | Required | Example Values |
|---|---|---|
| item_type | yes | screw, bolt, nut, outlet_cover, switch_plate, knob |
| size | yes | varies by item_type |
| material | optional | plastic, metal, brass, stainless |
| color_finish | optional | white, ivory, black, brushed_nickel |

---

## 22. MVP Prompt Specifications

### Vision Analyst Prompt

```
You are a home maintenance expert analyzing a photo. Describe exactly what you see:

1. What item is shown? (e.g., light bulb, battery, air filter, faucet, outlet cover)
2. What is wrong with it? (e.g., broken, burned out, cracked, missing, worn)
3. Read any visible text: brand names, model numbers, wattage, voltage, size markings.
4. Describe the physical characteristics: shape, color, size relative to surroundings, base/connector type.

Rules:
- Only report what is VISIBLE in the photo. Do not guess text you cannot read.
- If the image is blurry or unclear, say so and set confidence low.
- Do not recommend products. Only describe what you see.

Return a JSON object with: item_category, problem_type, visible_brand, visible_model, visible_text, description, confidence.
```

### Spec Extractor Prompt

```
You are a product specification expert. Given an issue analysis of a home item, determine the exact replacement product specifications.

Use the visible text, item category, and physical description to infer specs. For a light bulb, determine: base_type, wattage_equivalent, color_temperature_k, shape, technology, dimmable. For a battery, determine: size, chemistry, voltage.

Rules:
- Use visible text as primary evidence (e.g., "60W" on a bulb means 60W equivalent).
- Infer from physical characteristics when text is not visible (e.g., standard US ceiling fixture → likely E26).
- Set confidence per field. If you are guessing, confidence must be below 0.7.
- Generate clarification questions for any critical field with confidence below 0.7.
- Generate a search_query string suitable for searching a shopping site.

Return a JSON object with: item_category, attributes, confidence_per_field, clarification_questions, search_query.
```

---

## 23. MVP Test Plan

### Unit Tests

- Photo validation: rejects bad formats, oversized files, missing files.
- Schema validation: all Pydantic models serialize/deserialize correctly, including new PipelineStage, ChatMessage, and PipelineResult with messages.
- Ranking engine: deterministic scoring given same inputs; higher spec match → higher rank.
- Order confirmation gate: only "yes"/"y" proceeds; everything else blocks.
- Pipeline stage tests:
  - `start_session` blocks at `CLARIFYING` when spec extractor returns clarification questions.
  - `start_session` proceeds to `RESULTS` when no clarification is needed.
  - `advance` from `CLARIFYING` re-runs spec extraction with user context and proceeds to `RESULTS`.
  - `advance` from `RESULTS` with refinement feedback re-searches and returns updated products.

### Integration Tests

- End-to-end pipeline with a fixture photo and mock search results.
- Vision Analyst returns valid JSON matching IssueAnalysis schema.
- Spec Extractor returns valid JSON matching ProductSpec schema.
- Product Searcher handles API errors gracefully (returns empty list, not crash).
- Full session is saved to JSON and can be reloaded with conversation transcript intact.
- Web `/chat` endpoint correctly advances a session from `CLARIFYING` to `RESULTS`.
- Web `/chat` endpoint correctly handles refinement from `RESULTS` back to `RESULTS`.

### LLM Contract Tests

- Invalid JSON from LLM is retried or repaired.
- Vision Analyst does not recommend products (only describes).
- Spec Extractor generates clarification questions when confidence is low.
- Spec Extractor search_query is non-empty for all supported categories.

### Manual Test Matrix

| Photo | Expected Category | Expected Key Spec | Pass Criteria |
|---|---|---|---|
| Burned-out A19 bulb with visible text | bulb | E26, 60W | Correct base + wattage |
| CR2032 battery in remote | battery | CR2032 | Correct size |
| HVAC filter with size printed | filter | Correct dimensions | Matches printed size |
| Blurry photo of ceiling light | bulb | Low confidence | Asks for better photo |
| Photo of a faucet handle | hardware/other | Identifies item | Does not crash |

---

## 24. MVP Roadmap

### Phase 1: Skeleton (Week 1)

- Repository setup, configs, schemas.
- Pipeline runner with stub modules.
- SQLite storage layer.
- CLI entry point.

### Phase 2: Vision + Specs (Week 2)

- Vision Analyst agent with LLM integration.
- Spec Extractor agent with clarification loop.
- Prompt engineering and testing with sample photos.

### Phase 3: Search + Ranking (Week 3)

- Product Searcher with SerpAPI or mock data.
- Product Ranker with weighted scoring.
- Terminal presentation of ranked results.

### Phase 4: Ordering + Storage (Week 4)

- Order Manager with confirmation gate.
- Mock order placement.
- Full session persistence and replay CLI.

### Phase 5: Polish + Evaluation (Week 5)

- Test with 20+ real photos across categories.
- Measure accuracy metrics.
- Fix failure modes discovered in testing.
- Documentation.

### Phase 6: Interactive Conversation + Chat UI (Week 6)

- Refactor pipeline from monolithic to incremental stage-based execution (`pipeline.py`).
- Add `PipelineStage` enum, `ChatMessage` model, and conversation transcript to `PipelineResult`.
- Implement blocking clarification: pipeline pauses at `CLARIFYING` until user answers.
- Implement refinement loop: user can send follow-up messages from `RESULTS` to re-search.
- Add `/chat` endpoint to web server for session-based message exchange.
- Rebuild web UI as chat-driven interface with sidebar, message bubbles, progressive disclosure.
- Update CLI to support clarification prompts and `refine <criteria>` command.
- Both CLI and web UI share the same `pipeline.py` functions for consistent behavior.

---

## 25. MVP Engineering Tickets

### EPIC 1: Core Platform

- Define Pydantic schemas for all data models.
- Create SQLite database layer (create tables, CRUD operations).
- Build config loader (categories.yaml, ranking.yaml, retailers.yaml).
- Build pipeline runner (main.py) with step orchestration.
- CLI argument parsing (photo path, optional description, replay mode).

### EPIC 2: Photo Intake

- Photo validation (format, size).
- Copy to session directory.
- Store Photo record in database.

### EPIC 3: Vision + Spec Extraction

- Vision Analyst agent: LLM vision call, JSON parsing, retry on bad output.
- Spec Extractor agent: LLM call, confidence scoring, clarification question generation.
- Clarification loop: terminal prompt, re-run extractor with user input.
- Prompt files for both agents.

### EPIC 4: Product Search + Ranking

- Product Searcher: SerpAPI integration (or mock adapter).
- Result normalization: map API response to ProductResult schema.
- Product Ranker: weighted scoring engine.
- Terminal presentation: formatted product comparison display.

### EPIC 5: Order Management

- Order confirmation gate: display summary, require explicit "yes."
- Order placement: retailer API call (or mock).
- OrderRecord storage.
- Order status display.

### EPIC 6: Storage + Replay

- Session save: all artifacts per session to SQLite + filesystem.
- Session list: show past sessions with date, category, status.
- Session replay: load and display a past session's analysis, specs, results, and order.

### EPIC 7: Testing + Quality

- Unit tests for all modules.
- Integration test with fixture photos and mock search.
- LLM contract tests.
- Sample photo fixtures for each supported category.

### EPIC 8: Interactive Conversation + Chat UI (v1.1)

- Define PipelineStage enum and ChatMessage model in schemas.
- Build incremental pipeline engine (`pipeline.py`) with `start_session` and `advance` functions.
- Implement blocking clarification: `start_session` pauses at CLARIFYING if spec extractor returns questions.
- Implement refinement: `advance` from RESULTS appends user feedback to search query and re-runs search/rank.
- Add `/chat` POST endpoint to web server.
- Rebuild web UI as chat-driven interface: sidebar with session history, message bubbles, progressive disclosure of analysis → specs → clarification → products, context-aware input bar.
- Update CLI to support blocking clarification loop and `refine <criteria>` command.
- Add pipeline stage tests (blocking, proceeding, advancing, refinement).

---

## 26. Acceptance Criteria for MVP Launch

The MVP is launch-ready when:

1. `python -m src.main analyze <photo_path>` produces a ranked product list for a clear photo of a supported item.
2. Each product recommendation includes the spec match reason and price.
3. The confirmation gate blocks order placement until the user explicitly types "yes."
4. All intermediate artifacts (analysis, specs, search results, order) are stored and retrievable.
5. `python -m src.main history` lists past sessions.
6. `python -m src.main replay <session_id>` shows the full pipeline output of a past session.
7. The system handles unclear photos gracefully (asks for better photo or clarification).
8. At least 80% accuracy on primary spec extraction across 10 test photos of supported categories.
9. When the spec extractor has clarification questions, the pipeline blocks and does not search until the user answers (both CLI and web UI).
10. The user can refine product results by sending follow-up messages (e.g., "I need dimmable") without re-uploading the photo.
11. The web UI displays the full conversation transcript and allows loading past sessions from the sidebar.
12. The conversation transcript (all messages with roles and timestamps) is persisted as part of the session JSON.

---

## 27. Open Questions

1. ~~Which retailer API to use for product search?~~ **Resolved:** Three-tier strategy — SerpAPI for Google Shopping when API key is set, curated mock fixtures for known categories, LLM-generated product suggestions as final fallback.
2. Should the system support multiple items per photo (e.g., a photo showing 3 different broken things)?
3. How should payment/shipping be handled? Pre-configured retailer account? OAuth flow? For MVP, mock is acceptable.
4. ~~Should the system learn from past corrections (user says "that's wrong, it's actually GU10")?~~ **Partially resolved:** The refinement loop allows users to correct the system's recommendations in the current session. Cross-session learning remains out of scope.
5. What is the acceptable LLM cost per session? Vision calls are more expensive than text-only.
6. Should the system support non-English labels on products (e.g., imported bulbs with Chinese text)?

---

## 28. Appendix: Example End-to-End Session

### CLI Session with Clarification and Refinement

```
$ python -m src.main analyze photos/broken_bulb.jpg --description "kitchen ceiling light burned out"

🔍 Analyzing photo...

📋 Issue: bulb — burned_out (confidence: 92%)
   A burned-out A19 light bulb in a standard ceiling fixture. The base is E26 screw type.
   Visible text: 60W, E26

🔧 Specs: E26 60W A19 LED bulb 2700K
   base_type: E26 (95%)
   wattage_equivalent: 60 (90%)
   color_temperature_k: 2700 (85%)
   shape: A19 (80%)
   technology: LED (70%)
   dimmable: unknown (50%)

❓ Please answer:
   Is this bulb on a dimmer switch?

> No, it's a regular switch

🔧 Specs: E26 60W A19 LED bulb 2700K non-dimmable
   ...
   dimmable: false (95%)

🛒 Top 3 products:
   1. Philips LED A19 60W Equivalent Soft White 2700K (4-pack)
      $8.97 | ⭐4.7 (12340 reviews) | Score: 0.87
      Strong spec match. Highly rated (4.7⭐). In stock
   2. Amazon Basics A19 LED 60W 2700K (6-pack)
      $11.49 | ⭐4.5 (8200 reviews) | Score: 0.82
      Strong spec match. Good price. In stock
   3. Cree A19 LED 60W 2700K
      $4.97 | ⭐4.8 (6100 reviews) | Score: 0.79
      Strong spec match. Highly rated (4.8⭐). In stock

💾 Session: a1b2c3d4e5f6

Select product (1-5), 'refine <criteria>', or 'q' to quit: refine I want dimmable actually

🛒 Top 3 products:
   1. Philips LED A19 60W 2700K Dimmable
      $5.49 | ⭐4.8 (9200 reviews) | Score: 0.89
      ...

Select product (1-5), 'refine <criteria>', or 'q' to quit: 1

📦 Order: Philips LED A19 60W 2700K Dimmable
   Total: $5.49
   Place order? (yes/no): yes
   ✅ Order placed! ID: MOCK-A1B2C3D4
```

### Web Chat Session

The web UI presents the same flow as a chat conversation:

1. User uploads photo and optionally types a description.
2. System shows analysis as a chat message with confidence badge.
3. System shows extracted specs as an embedded table card.
4. If clarification is needed, system asks questions in a chat bubble. The input bar placeholder changes to "Answer the questions above..." and the pipeline **blocks** — no products are shown until the user responds.
5. User types an answer. System re-extracts specs and proceeds to search.
6. Products appear as embedded cards with Buy buttons.
7. User can type refinement messages (e.g., "show me cheaper options") to re-search.
8. User clicks Buy → browser `confirm()` dialog → order placed → order confirmation card appears.
9. Past sessions are listed in the sidebar and can be loaded to view the full conversation transcript.
