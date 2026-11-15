# Khaleev — SPEC

## Objective

Khaleev is a single-user, local-first document Q&A application. The user uploads PDFs, asks natural-language questions against one selected document, and receives answers that always cite the source page number(s) the answer was drawn from. To differentiate from generic RAG demos, Khaleev ships an evaluation layer: a curated golden Q&A set per document, on-demand computation of retrieval hit rate and answer faithfulness, and a dashboard showing each eval run's metrics with history across runs (U).

The user is a single technical person running the app entirely on their own machine (U). Success looks like: upload a PDF → ask a question → get a page-cited answer → run an eval → see both metrics on a dashboard with run-over-run comparison (U).

## References

No external references were supplied for the product idea itself. The only source of truth for the product is the verbatim user statement: "Document Q&A with citations: Upload PDFs, ask questions, get answers with source page references. Add evaluation (retrieval hit rate, answer faithfulness) to stand out. called Khaleev" (R/U), refined by one interview round whose answers are recorded in `## Locked intent` (U). `docs/references/` exists at the project root for future references; it is currently empty. No reference entries are invented.

Two **visual** references were supplied later (2026-11-13) and are recorded below; they affect presentation only, not the product requirements above.

| ID | Source | What it establishes | Access date |
|---|---|---|---|
| R1 | User attachment "image-2.png" (dashboard layout mockup) | The dashboard page's **layout structure only**: overall frame, left icon rail, top bar, two-column main grid, card shapes, section rhythm, type scale and spacing (full structural description below) | 2026-11-13 |
| R2 | `D:\SYSTEM\Downloads\Color Hunt Palette f3f4f4853953612d532c2c2c.png` (Color Hunt palette) | The locked four-colour palette `#F3F4F4`, `#853953`, `#612D53`, `#2C2C2C`, its role mapping and contrast floors (below) | 2026-11-13 |

### R1 — layout description (the contract)

The build agents cannot see the image; this description is the binding contract. It is faithful to the reference and nothing more.

**Overall frame.** A single large rounded panel (radius ~28px), inset ~24px from a tinted page background, with a very soft single-layer shadow. Inside the panel, a slim vertical icon rail on the far left, then the content area. No page-level header bar outside the panel; no sidebar labels, no sidebars with text.

**Left icon rail** (~72px wide, full panel height): brand mark at the top (a compact square glyph), then a vertical stack of 5–6 icon-only buttons at ~24px glyph size, one of which is active. The active item is a ~40x40 rounded square (radius ~10px) filled with the dark accent, white glyph; inactive items are glyph-only with no background and no border. The rail has no dividing border, only whitespace.

**Top bar** (spans the content area): on the left a pill search field (fully rounded, pale fill, magnifier glyph left, placeholder text, ~44px tall, flexible width up to roughly 640px). On the right a cluster of two circular icon buttons (~40px, pale fill) then one circular avatar (~40px).

**Main area** — a two-column grid with ~24px gap, left column ~65%, right column ~35%, both stacking vertically.

Left column, in order:
1. **Hero banner card**: pale tinted fill (a low-opacity tint of the dark accent), radius ~20px, padding ~28px, min-height ~150px. Left: a two-line headline at ~22px semibold, then a dark pill CTA button (~40px tall, white text). Right: a decorative illustration region ~250px wide with abstract shapes in palette tones.
2. **Section heading row**: title on the left (~18–20px semibold) with an optional "see all" text link on the right.
3. **Three equal cards in a row** (the reference's "Your progress" cards): each has an icon chip at top-left in a white circle, an overflow "..." button at top-right, a two-line title, then a progress row: a small "Progress" label left, a thin (~6px) fully rounded track with a filled portion, and a percentage right-aligned. Radius ~16px, padding ~16px, each card a different pale tint.
4. **Another section heading row**, then **two cards side by side**: each has an illustration panel across the top (~110px, pale tint, rounded top corners), then a two-line semibold title, then a meta row of small outline chips with icon + short text.

Right column, in order:
1. **Month/calendar card**: header row with two circular ghost arrow buttons and a centred month-and-year label; a row of seven weekday initials; then six square date tiles in a row, one active (filled with the dark accent, white numeral), others plain. Radius ~16px, padding ~16px.
2. **Section heading row**.
3. **Two stacked cards** (the reference's course cards): a row of two small tag pills (pale fill, tiny text), a title (~16–18px semibold) with a right-aligned value, a two-line muted description, a meta row of two small icon-plus-text items, and a footer with a cluster of small overlapping circular avatars on the left and a dark pill button on the right.

**Type and spacing.** One sans-serif family. Card titles 15–17px semibold; body 13–14px; meta 12px muted. Vertical rhythm: 16–24px between cards, 8–12px inside them. Radii: cards 16–20px, buttons pill, icon buttons 40px circles. Shadows: one very soft layer, low opacity. Light theme only.

**R1 states explicitly: the layout only.** Do not copy the reference's content, copy, illustrations, brand marks, calendar, prices, avatars or course cards. The structure, proportions, card shapes, rail, top bar and section rhythm are what is adopted.

**Deviation from R1 — user-approved (2026-11-14).** Locked intent 17 deliberately deviates from R1 on the landing page and in the shell: the top bar (pill search, circular icon buttons, avatar) is removed entirely, and the Library page's two-across/right-column extras (golden-set and document-detail cards, latest-eval-run card, hero illustration blob) are dropped, leaving upload + document list. This deviation is user-approved; no later task may restore the top bar, avatar, search-in-top-bar or landing extras "for fidelity" to R1. R1 remains binding for everything else: the inset panel frame, the icon rail, card shapes, type scale and section rhythm on the non-landing pages.

### R2 — palette (locked)

Swatches in order: `#F3F4F4`, `#853953`, `#612D53`, `#2C2C2C`.

Roles:
- `#F3F4F4` — page canvas and pale surfaces;
- `#FFFFFF` — raised cards;
- `#2C2C2C` — primary text and the "dark pill" buttons / active nav;
- `#612D53` — primary accent (active rail item, key buttons, focused emphasis);
- `#853953` — secondary accent (progress fills, tags, highlight tints).

Pale tints are produced by mixing an accent with white at low opacity — decorative only, never the sole carrier of meaning.

Measured contrast ratios (WCAG relative-luminance formula; recorded so no later task silently picks something prettier and fails AA):
- `#2C2C2C` ink on `#F3F4F4` canvas — 12.7:1
- `#2C2C2C` ink on `#FFFFFF` card — 14.0:1
- `#FFFFFF` on `#612D53` primary — 10.5:1
- `#FFFFFF` on `#853953` secondary — 7.8:1

Floors: body text ≥ 4.5:1; interactive boundaries ≥ 3:1.

## Locked intent

Every item below is fixed by the user statement or interview answers and may only change via the change log.

1. **PDF upload** — the user can upload PDF files through the UI into local storage (U).
2. **Page-level extraction preserving page numbers** — text is extracted per page; every extracted chunk retains its 1-based source page number (U).
3. **Natural-language Q&A over one selected document** — a question is answered using only the chunks of the currently selected document (U).
4. **Mandatory citations** — every answer carries citations naming the source page number(s) it was drawn from; an answer without page citations is a defect (U).
5. **Retrieval hit rate metric** — computed for eval runs against the golden set (U); precisely defined in `## Metric definitions`.
6. **Answer faithfulness metric** — computed for eval runs against the golden set (U); precisely defined in `## Metric definitions`.
7. **Eval dashboard** — shows per-run metrics and comparison history across eval runs (U).
8. **Golden set** — a curated Q&A set per document, with each entry containing a question, expected answer, and expected page number(s) (U).
9. **Single-user local operation** — one user, one machine, all data stored locally; no accounts, no auth, no multi-tenancy (U).
10. **Local-first models** — local embeddings via sentence-transformers; generator is local Ollama by default with optional cloud API key if the user supplies one (U).
11. **Zero required API keys** — the app must be fully functional with no API keys configured (U).
12. **Tests never hit the network** — the test suite runs entirely offline, including model-backed paths (U).
13. **No authentication** — no login, tokens, or session security; this is explicitly out of scope (U).
14. **Dashboard layout structure (R1)** — the UI adopts the R1 layout structure as described in `## References → R1`: the inset rounded panel frame, the left icon rail (icon-only buttons, one active as a filled rounded square), the pill search top bar with circular icon buttons and avatar, the ~65%/~35% two-column main grid with ~24px gap, and the card/section rhythm and type scale stated there. This is the layout contract for the dashboard page; other pages reuse the same frame, rail, top bar and card language.
    **Amended in place, 2026-11-14:** the clauses naming the top bar, the circular icon buttons, the avatar and the pill search in the top bar — and the two-across/right-column landing composition — are **superseded by locked intent 17** (minimal landing page and top-bar removal). The original text above is kept so the history stays readable. Still in force from this item: the inset rounded panel frame, the left icon rail, the two-column main grid with ~24px gap, and the card/section rhythm and type scale, applied to pages other than the landing page (see 17).
15. **Colour palette and contrast floor (R2)** — the UI uses exactly the four-colour palette `#F3F4F4`, `#853953`, `#612D53`, `#2C2C2C` with the role mapping and the measured contrast ratios recorded in `## References → R2`. Body text must stay ≥ 4.5:1 and interactive boundaries ≥ 3:1; pale tints are decorative only and never the sole carrier of meaning. Light theme only.
16. **Layout only — no copied content (R1)** — the R1 reference is adopted for structure, proportions, card shapes, rail, top bar and section rhythm only. The reference's content, copy, illustrations, brand marks, calendar, prices, avatars and course cards must not be reproduced; all content comes from Khaleev's own features (F1–F6).
17. **Minimal landing page and simplified shell ("Minimal landing — upload + documents", 2026-11-14)** — the landing (Library) page is upload + document list, nothing else, and the shell loses its top bar:
    - **Landing page contents** (U): the Library page contains only the hero banner, the upload control, and the "Your documents" document list. Removed from the landing page: the "Selected document" two-across row (the golden-set revision/entry-count card and the document-detail/content-hash card), the "Latest eval run" card, and the decorative illustration blob in the hero.
    - **Hero simplified** (U): the hero is a short banner of a headline, one supporting line, and the `Upload PDF` button. The redundant triple is dropped (no "Upload a PDF" label plus helper sentence under the button), and "and evaluation metrics" is dropped from the headline (the eval dashboard explains itself). The promise text must keep `page-cited answers` as one unbroken text node, because `App.test.tsx` asserts it.
    - **Search relocated and conditional** (U): the search field is removed from the global top bar and rendered only on the Library page, inside the "Your documents" section header, and **only when at least one document exists** — on an empty library it must not be rendered. It filters the list client-side by case-insensitive title, issues no request, and is labelled `Search documents`.
    - **Top bar removed** (U): with search, the two duplicate circular icon buttons ("Go to Library", "Go to the Eval dashboard") and the decorative avatar gone, the top bar has nothing left and is removed entirely. The shell becomes: inset rounded panel + icon rail + page content. The rail is kept exactly as it is: brand mark, three icon-only links named `Library`, `Chat`, `Eval dashboard`, `aria-current` on the active one, `Primary` landmark.
    - **Stale selection discarded silently** (A — flagged as an assumption made during browser verification): if the persisted selected document id is not present in the current `GET /api/documents` list, the selection is cleared and the empty state is rendered. No error text anywhere (no "document … does not exist" in the Library eval/golden-set/detail cards, the eval dashboard, or the Chat "Q&A target" strip). Empty states are plain and instructive: Library → "No documents yet. Upload a PDF to start your library."; Chat and Eval dashboard → "No document selected" plus a link back to the Library. A genuine network or server failure may still surface an error — only the "document no longer exists" case is silent.
    - **Scope guard** (U): no functional change to upload, ingest, ask, citations, the page viewer, eval runs, metrics, comparability or any backend behaviour; no new npm dependency, no new colour, no dark mode. Pre-existing test files stay green and unedited; only the four redesign test files (`AppShell.test.tsx`, `Library.cards.test.tsx`, `Chat.layout.test.tsx`, `EvalDashboard.layout.test.tsx`) may change, because they assert on the removed parts. Rails, Chat and Eval dashboard keep their structure and their accessible names, roles and ARIA.

## Open to suggestions

- SUGGESTION: Default retrieval chunk size ~400–800 characters with 10–15% overlap. Reason: page-granular chunks alone are too coarse for precise retrieval; fixed-size overlapping chunks keep page attribution. Trade-off: a tunable constant that must be re-tuned if embedding model changes.
- SUGGESTION: Sentence-transformers model `all-MiniLM-L6-v2` as the default embedding model. Reason: small (~80 MB), fast on CPU, widely used, no network after first download. Trade-off: user can swap it via config; model download on first run is a network event outside tests.
- SUGGESTION: SQLite via SQLAlchemy for documents/chunks/evals; vectors in a local FAISS index file per document (or one index with doc-id filter). Reason: durable metadata + fast local ANN search without a server. Trade-off: FAISS adds a dependency; sqlite-vss is an alternative but less maintained.
- SUGGESTION: Top-k default k=5 for retrieval during Q&A and eval. Reason: small enough to keep context short, large enough to hit relevant pages. Trade-off: k must be fixed for hit-rate@k to be comparable across runs.
- SUGGESTION: Ollama model default `llama3.1:8b` (configurable). Reason: good local quality/size balance. Trade-off: ~5 GB disk; user may prefer a smaller model.
- SUGGESTION: Faithfulness scorer = local NLI via a small sentence-transformers cross-encoder (e.g. `cross-encoder/nli-deberta-v3-small`) with keyword-overlap fallback. Reason: runs offline and satisfies "tests never hit the network"; NLI is the cheapest defensible entailment signal. Trade-off: NLI models misjudge some paraphrases; the fallback and human review of eval runs mitigate this. This makes the scorer a concrete, unit-testable component instead of a vague "LLM judge".
- SUGGESTION: Golden set stored as a human-editable JSON file per document under the data directory. Reason: curated content must be inspectable and diffable. Trade-off: no UI for editing golden sets in v1 (edit by hand).
- SUGGESTION: Re-purpose the R1 calendar slot as the eval-run history card — the calendar card's position and shape (header row with ghost arrows, centred label, grid of small tiles) becomes a run-history grid where each small tile is an eval run, active tile = latest run. Reason: keeps the R1 right-column rhythm without shipping a decorative calendar that has no owner feature. Trade-off: the "calendar" visual becomes a grid of run tiles, which reads slightly less literally than the mockup.
- SUGGESTION: Render the top-bar avatar as a static placeholder glyph (initial-free generic user icon, no menu) since there is no auth and no user record. Reason: keeps the R1 top-bar composition without inventing identity state the product does not have (locked intent 9/13). Trade-off: the avatar is inert chrome; if the user later wants a settings entry point, it would change this. **Moot as of 2026-11-14:** locked intent 17 removes the top bar and avatar entirely, user-approved.
- SUGGESTION: Build the hero-banner and side-by-side card illustration regions as small abstract inline-SVG shapes in palette tones, and keep them optional — if they look noisy, ship the cards without the illustration region. Reason: R2 palette tones are enough for decoration; inline SVG adds no dependency (locked intent on no new npm packages). Trade-off: hand-drawn SVG costs build time; omitting them makes the layout plainer than the mockup. **Moot as of 2026-11-14:** locked intent 17 removes the hero illustration blob from the landing page, user-approved; any illustration region elsewhere remains optional per this suggestion's own terms.
- SUGGESTION: Collapse the icon rail to a bottom bar on small screens (≤ ~480px). Reason: at 360px the ~72px vertical rail eats ~20% of the viewport width before the content starts; a bottom bar frees the full width for page content. Trade-off: a second nav implementation to test (duplicated ARIA structure), and it diverges from R1's desktop-only rail composition; the current app already fits at 360 without overflowing, so this is polish, not a defect.
- SUGGESTION: Show a document count in the "Your documents" section header (e.g. "Your documents (4)"). Reason: cheap reassurance that the upload succeeded without scrolling the list, and it pairs naturally with the relocated search field in the same header. Trade-off: one more derived value that must stay in sync with the list (a stale count after delete would look like a defect) and one more assertion surface in tests.

## Core features

- **F1 — PDF upload & ingest** (U): Upload one or more PDFs via the UI; the backend extracts text per page (1-based page numbers), splits pages into chunks that each carry `(document_id, page_number, chunk_index)`, embeds chunks locally, and writes them to SQLite + the vector index. Ingest is idempotent per document (re-upload of the same file replaces the prior document's data, keyed by content hash).
- **F2 — Document library** (U): List uploaded documents (title, page count, ingest date, eval status); select one document as the Q&A target; delete a document (removing its chunks, index entries, and eval history).
- **F3 — Q&A with citations** (U): For the selected document, embed the question, retrieve top-k chunks, build a prompt requiring page-cited answers, generate via the configured generator (Ollama default, cloud optional), and return the answer text plus structured citations `[{page: int, quote: str}]`. The UI renders the answer with page references; clicking a citation opens the document viewer at that page.
- **F4 — Golden set management** (U): For each document, maintain a curated golden set: entries of `{question, expected_answer, expected_pages: [int]}`. Editable as JSON on disk (see suggestions); shown in the UI as read-only per document.
- **F5 — Eval runs** (U): On demand, run an evaluation: for each golden entry, retrieve top-k chunks (retrieval metrics) and generate an answer (faithfulness metrics). Persist one eval-run record with per-entry results and aggregate metrics, plus a timestamp and the config used (k, models).
- **F6 — Eval dashboard** (U): Show the latest eval run's retrieval hit rate and answer faithfulness; show history: a list of past runs with their metrics and timestamps so the user can compare across runs (e.g. after changing k or the embedding model).

## Metric definitions

These definitions are the contract for unit tests. All metrics are floats rounded to 4 decimal places (half-up) at persistence and display (A).

**Retrieval hit rate @ k** (U, A): For a golden entry with expected pages `E` (set of 1-based page ints), retrieve the top-k chunks for the entry's question. The entry *hits* iff at least one retrieved chunk has `page_number ∈ E` (page-level matching: a chunk matches if its page number is in the expected set, regardless of which part of the page the chunk came from). `hit_rate@k = (# entries that hit) / (# entries in golden set)`. If the golden set is empty, the metric is undefined and the run is rejected. k is recorded per run; the default k=5 (A).

**Answer faithfulness** (U, A): For each generated answer, the scorer decomposes the answer into claims (sentences that assert content; a sentence is one claim). A claim counts as *supported* iff the scorer judges it entailed by (a) the retrieved chunk(s) cited in the answer or, if the generator cited nothing, (b) all top-k retrieved chunks. Judgement is made by a local entailment scorer (A — see suggestion); each claim receives a binary supported/unsupported decision. `faithfulness = (# supported claims) / (# claims)` across all entries of the run. An answer with zero claims scores 0.0. The scorer, its model id, and its version are persisted with the run so scores are comparable only within the same scorer (A).

**History comparability** (A): Two eval runs are comparable in the dashboard if they share the same golden set revision, k, embedding model, and scorer. The dashboard flags runs with differing configs rather than silently charting them together.

**Worked example** (A): Golden entry: question "What penalty applies to late filings?", `expected_pages: [4]`. The eval retrieves top-5 chunks whose pages are `4, 4, 3, 4, 9`. Since `4 ∈ top-k pages`, the entry hits. The generated answer "Late filings incur a flat 200 credit penalty per return" is split into one claim; the scorer judges it against the chunk from page 4 that the citation names. If entailed, the entry contributes `claims=1, supported=1` → entry faithfulness 1.0. If the run has 10 entries, 7 hit, and total supported claims are 15 of 20, the run persists `hit_rate@5 = 0.7000`, `faithfulness = 0.7500`.

## Stack and constraints

- **Stack** (U): FastAPI (Python 3.11+) backend; React + Vite + TypeScript frontend; SQLite for metadata (documents, chunks, golden sets, eval runs); local vector index (FAISS or equivalent local file-based ANN) for embeddings; sentence-transformers for local embeddings; Ollama as the default answer generator, optional cloud API (key supplied by user) as an alternative generator.
- **Single repo** (U): monorepo with `backend/` (FastAPI app, `src/khaleev/…`) and `frontend/` (React app); single process model: `uvicorn` serves the API and the built frontend, or `vite dev` proxies to the API during development.
- **Local-only data** (U): all data under a single local data directory (SQLite file, PDF originals, vector index files, golden-set JSON files). No cloud storage.
- **Visual design constraints** (U, R1, R2): the R2 palette (`#F3F4F4` / `#853953` / `#612D53` / `#2C2C2C`, roles and contrast floors per `## References → R2`) **supersedes the earlier T21 visual direction** (`#1d4e89` accent on `#f6f5f1`), which is no longer the target. No new npm dependency may be added for the redesign — no UI framework, no icon package; glyphs are inline SVG. Existing roles, text content, and ARIA semantics must not change: the redesign restyles presentation only and every functional acceptance criterion (1–11) stands unchanged.

**Project tree** (A):

```
khaleev/
├── backend/
│   ├── src/khaleev/
│   │   ├── api/          # FastAPI routers, Pydantic request/response models
│   │   ├── ingest/       # PDF parsing, page extraction, chunking, embedding, indexing
│   │   ├── retrieval/    # vector index wrapper, top-k search, page filtering
│   │   ├── generation/   # Ollama client, optional cloud client, citation parsing
│   │   ├── evals/        # golden-set loading, hit-rate + faithfulness scoring, run persistence
│   │   ├── models/       # SQLAlchemy ORM models + migrations
│   │   └── config.py     # data dir, model names, k, generator selection
│   └── tests/            # pytest; offline; temp data dir fixture
├── frontend/
│   └── src/
│       ├── api/          # typed REST client mirroring backend Pydantic models
│       ├── components/   # Upload, DocumentList, AskPanel, CitationList, PageViewer
│       ├── pages/        # Library, Chat, EvalDashboard
│       └── types/        # shared TS types
└── docs/references/      # future reference material (empty today)
```

**Data model** (A): `documents(id, content_hash UNIQUE, title, page_count, created_at)`; `chunks(id, document_id FK, page_number, chunk_index, text, embedding_ref)`; `golden_sets(document_id FK, revision, path, entries JSON)`; `eval_runs(id, document_id FK, created_at, k, embedder_id, scorer_id, hit_rate REAL, faithfulness REAL, config JSON)`; `eval_run_entries(run_id FK, golden_index, hit BOOL, answer TEXT, claims INT, supported_claims INT, faithfulness REAL)`. PDF originals, the vector index, and golden-set JSON live on disk; SQLite holds metadata and metrics only.

**API surface** (A): `POST /api/documents` (multipart upload, 201, content-hash dedupe → 200 with existing id); `GET /api/documents` (list); `GET /api/documents/{id}` (detail); `DELETE /api/documents/{id}`; `GET /api/documents/{id}/pages/{n}` (extracted text); `POST /api/documents/{id}/ask` → `{answer, citations: [{page, quote}]}`; `GET /api/documents/{id}/golden` (golden set, read-only); `POST /api/documents/{id}/evals` (start run, k configurable, default 5); `GET /api/evals/{run_id}` (full run + per-entry results); `GET /api/documents/{id}/evals` (history list); `GET /api/config` / `PUT /api/config` (k, embedder, generator choice). All responses are typed Pydantic models.
- **Commands** (A): backend `uv run uvicorn khaleev.app:app --reload --port 8000`; frontend `npm run dev` / `npm run build`; tests backend `uv run pytest` and frontend `npm test`; lint backend `uv run ruff check .`, frontend `npm run lint`.
- **Project layout** (A): see the project tree above; `frontend/src/api/` is a generated or hand-written typed client for the REST endpoints; `docs/references/` for future reference material.
- **Code style** (A): Python — `ruff` (line length 100, type hints required on public functions), pytest fixtures over classes; TypeScript — strict mode, `prettier` + `eslint`, function components with typed props; REST endpoints return typed Pydantic models that mirror the frontend TS types.
- **Testing strategy** (A): pytest with three levels — (1) unit tests for chunking, page attribution, hit-rate@k, claim splitting, and faithfulness math on constructed inputs (no models loaded); (2) integration tests exercising the FastAPI app end to end with a stubbed generator and a deterministic fake embedding function, against a temp data directory; (3) one optional manual end-to-end check against real Ollama, documented in the README and never part of CI. Frontend: `npm test` with vitest + React Testing Library for components and the API client. No test in either suite performs a network call: the Ollama client and any cloud client are always injected/mocked in tests, and the embedding function is replaceable so tests use a deterministic fake.

## Boundaries

- **Always**:
  - run the full offline test suite (`uv run pytest`, `npm test`) before declaring any feature done;
  - attach a page number to every chunk and every citation — a chunk or citation without a page number is a defect;
  - persist eval runs (never compute metrics only in memory);
  - keep the app runnable with zero API keys;
  - keep tests free of network access: mock or fake every model-backed path (generator, embedder, scorer);
  - record the config (k, embedder id, scorer id, golden-set revision) with every eval run.
- **Ask first**:
  - adding a new runtime dependency (Python or npm);
  - changing the SQLite schema after the first migration;
  - changing the metric definitions, the rounding rule, or the default k;
  - enabling cloud generators by default or adding another generator backend;
  - adding a background worker process or scheduler.
- **Never**:
  - require an API key to run core features;
  - send document content anywhere off-machine unless the user explicitly configures a cloud generator;
  - introduce auth, accounts, or multi-user state;
  - delete eval history when a document is re-ingested unless the document content changed;
  - let tests write to the user's real data directory (tests use a temp data dir);
  - ship an answer without citations or cite a page whose chunk was not in the retrieval context.

## Acceptance criteria

1. **Upload & ingest** (U): Given a real multi-page PDF, `POST /api/documents` with the file returns `201` with `{id, title, page_count}`, the PDF is stored locally, and `GET /api/documents/{id}/pages/3` returns non-empty extracted text whose chunks all carry `page_number == 3`. A second upload of the identical file does not create a duplicate document (content-hash dedupe).
2. **Q&A with citations** (U): With a document selected, `POST /api/documents/{id}/ask` with a natural-language question returns `{answer, citations}` where `citations` is a non-empty list of `[{page, quote}]`, every `page` is a valid 1-based page of that document, and the UI displays the answer with clickable page references that open the viewer at the cited page.
3. **Zero-key operation** (U): With no API keys configured and Ollama running locally, criteria 1–2 pass end to end; the UI shows no key-related errors.
4. **Golden set** (U): A golden set JSON for a document with ≥ 3 entries (`question`, `expected_answer`, `expected_pages`) loads and is visible in the UI for that document.
5. **Eval run produces both metrics** (U): Running an eval via `POST /api/documents/{id}/evals` returns a persisted run with `hit_rate@k` and `faithfulness` both present, both floats in `[0.0, 1.0]`, rounded to 4 decimals, and per-entry results retrievable via `GET /api/evals/{run_id}`.
6. **Dashboard history** (U): After ≥ 2 eval runs for a document, the dashboard shows the latest run's two metrics and a history list containing both runs with their metrics and timestamps; runs with different configs are flagged, not silently compared.
7. **Metric unit tests** (A): Unit tests verify hit rate @ k with a golden entry whose expected page appears in the top-k (→ hit) and one that does not (→ no hit), and verify the faithfulness denominator/rounding on constructed scorer outputs.
8. **Offline test suite** (U): `uv run pytest` and `npm test` pass with no network access (verified by running the suite with networking disabled or by mocking all external calls).
9. **End-to-end** (U): Upload a real PDF → ask a question → receive a page-cited answer → run an eval on that document → both metrics appear on the dashboard with history.
10. **Run comparability** (A): Two eval runs with identical golden-set revision, k, embedding model, and scorer appear in the history side by side; changing k to 10 between runs results in the second run being flagged in the dashboard, and the flagged state is computed from the persisted `config` fields, not from memory.
11. **Delete is complete** (A): `DELETE /api/documents/{id}` removes the SQLite rows (document, chunks, golden set, eval runs and entries), the vector-index entries, the stored PDF, and the golden-set file; a subsequent `GET /api/documents` no longer lists it and a re-upload of the same file starts fresh.

## Non-goals

- Authentication, accounts, multi-user or multi-tenant support (U).
- Cloud storage, sync, or any default off-machine data flow (U).
- Q&A across multiple documents simultaneously — one selected document per question (U).
- OCR or scanned-PDF text extraction (image-only pages) (A).
- Automatic golden-set generation or auto-scheduled evals; evals run on demand only (U).
- Production hardening: rate limiting, TLS, hardened headers, backups (A).
- Markdown/DOCX/HTML ingestion — PDF only (U).

## Assumptions

1. **A1** — "Source page references" means 1-based page numbers of the uploaded PDF, matching the PDF's own page order (not printed folio numbers).
2. **A2** — The answer generator (Ollama or cloud) is instructed via prompt to produce page-tagged citations, and the backend validates/repairs citations against retrieved chunk pages; unresolvable citations are dropped rather than shown as wrong pages.
3. **A3** — The local entailment scorer for faithfulness (see suggestions) is acceptable to the user; if the user prefers an LLM-judge, that changes the scorer component but not the metric definition.
4. **A4** — "Comparison history across runs" means a chronological list with values, not chart rendering, in v1.
5. **A5** — A machine able to run Ollama and sentence-transformers exists; minimum ~8 GB RAM is assumed.
6. **A6** — First-run model downloads (embedding model, Ollama pull) are permitted as one-time setup; tests still never download anything.

## Change log

| Date | Change | Source | Status |
|---|---|---|---|
| 2026-11-11 | Initial spec created from user statement and interview round | U | Establishes locked intent |
| 2026-11-13 | Visual redesign adopted: R1 dashboard layout (layout structure only) and R2 palette (`#F3F4F4`/`#853953`/`#612D53`/`#2C2C2C`) added as locked intent items 14–16. Supersedes the T21 visual direction (#1d4e89 accent on #f6f5f1 — not previously recorded in this spec). All functional requirements (citations guarantee, metrics, single-user local scope, offline tests, no-auth boundary) unchanged. | U (R1, R2) | Accepted |
| 2026-11-14 | Correction: R2 measured contrast ratio for `#2C2C2C` ink on `#FFFFFF` card was 13.6:1; recomputed with the WCAG 2.1 relative-luminance formula it is 13.97:1, rounded to **14.0:1**. Transcription error caught by verification (`frontend/src/styles/tokens.css` already recorded the correct 14.0:1); the other three R2 ratios (12.7:1, 10.5:1, 7.8:1) re-verified unchanged. No change to the palette, the role mapping, the contrast floors, or any requirement or acceptance criterion. | A | Accepted |
| 2026-11-14 | **Minimal landing — upload + documents.** User asked that only necessary user features be shown and the landing page be simpler to understand, then approved the scope named "Minimal landing — upload + documents". Locked intent **17** added: Library page reduced to hero + upload + document list (golden-set/detail two-across row, latest-eval-run card and hero illustration blob removed); hero reduced to headline + one supporting line + `Upload PDF` (keeps `page-cited answers` as one unbroken text node per `App.test.tsx`); search moved from the top bar into the "Your documents" section header, rendered only when ≥ 1 document exists; top bar removed entirely, rail unchanged; stale selected document id silently discarded and replaced by the empty states. Stale-selection defect found by browser verification of the running app (persisted selection survives document deletion / database reset, producing four error panes and a phantom Chat "Q&A target" strip); its service rule is recorded as an assumption (A). Item **14 amended in place** (top-bar/avatar/two-across clauses superseded by 17, original text kept); R1 deviation note added under `## References`; two now-moot suggestions annotated. **No functional requirement changed:** upload, ingest, Q&A, citations, page viewer, eval runs, metrics, comparability and all backend behaviour untouched; no new npm dependency, no new colour, no dark mode; pre-existing test files stay green and unedited, only the four redesign test files may change. | U (approved scope) + A (stale-selection rule) | Accepted |
| 2026-11-15 | **Cold-load stale selection (T28).** Task T28 added to the plan to close a gap in locked intent 17's stale-selection rule. The rule relied on the last loaded document list being available in module state, which a page reload discards: a cold load straight onto `/chat` therefore had nothing to reconcile against and rendered "Questioning Ghost Report.pdf · 4 pages" for a document that no longer exists (reproduced in the running app with a persisted id 999 and a direct `/chat` load). The selected-document store now persists the loaded list's **ids** beside the selection (`sessionStorage["khaleev.known-documents"]`, validated as numbers, corruption treated as no list) and reconciles a cold load against them; `clearSelectedDocument` forgets them. No request is added, no selection semantics change, and a stale id stays covered by the Library's next fetch and the ask endpoint's 404. Clause 17's rule text is unchanged; only its implementation is completed. No dependency, colour, dark mode, backend or request change. | A (implementation completion of locked intent 17's rule) | Accepted |
