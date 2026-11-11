# Khaleev — SPEC

## Objective

Khaleev is a single-user, local-first document Q&A application. The user uploads PDFs, asks natural-language questions against one selected document, and receives answers that always cite the source page number(s) the answer was drawn from. To differentiate from generic RAG demos, Khaleev ships an evaluation layer: a curated golden Q&A set per document, on-demand computation of retrieval hit rate and answer faithfulness, and a dashboard showing each eval run's metrics with history across runs (U).

The user is a single technical person running the app entirely on their own machine (U). Success looks like: upload a PDF → ask a question → get a page-cited answer → run an eval → see both metrics on a dashboard with run-over-run comparison (U).

## References

No external references were supplied. The only source of truth is the verbatim user statement: "Document Q&A with citations: Upload PDFs, ask questions, get answers with source page references. Add evaluation (retrieval hit rate, answer faithfulness) to stand out. called Khaleev" (R/U), refined by one interview round whose answers are recorded in `## Locked intent` (U). `docs/references/` exists at the project root for future references; it is currently empty. No reference entries are invented.

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

## Open to suggestions

- SUGGESTION: Default retrieval chunk size ~400–800 characters with 10–15% overlap. Reason: page-granular chunks alone are too coarse for precise retrieval; fixed-size overlapping chunks keep page attribution. Trade-off: a tunable constant that must be re-tuned if embedding model changes.
- SUGGESTION: Sentence-transformers model `all-MiniLM-L6-v2` as the default embedding model. Reason: small (~80 MB), fast on CPU, widely used, no network after first download. Trade-off: user can swap it via config; model download on first run is a network event outside tests.
- SUGGESTION: SQLite via SQLAlchemy for documents/chunks/evals; vectors in a local FAISS index file per document (or one index with doc-id filter). Reason: durable metadata + fast local ANN search without a server. Trade-off: FAISS adds a dependency; sqlite-vss is an alternative but less maintained.
- SUGGESTION: Top-k default k=5 for retrieval during Q&A and eval. Reason: small enough to keep context short, large enough to hit relevant pages. Trade-off: k must be fixed for hit-rate@k to be comparable across runs.
- SUGGESTION: Ollama model default `llama3.1:8b` (configurable). Reason: good local quality/size balance. Trade-off: ~5 GB disk; user may prefer a smaller model.
- SUGGESTION: Faithfulness scorer = local NLI via a small sentence-transformers cross-encoder (e.g. `cross-encoder/nli-deberta-v3-small`) with keyword-overlap fallback. Reason: runs offline and satisfies "tests never hit the network"; NLI is the cheapest defensible entailment signal. Trade-off: NLI models misjudge some paraphrases; the fallback and human review of eval runs mitigate this. This makes the scorer a concrete, unit-testable component instead of a vague "LLM judge".
- SUGGESTION: Golden set stored as a human-editable JSON file per document under the data directory. Reason: curated content must be inspectable and diffable. Trade-off: no UI for editing golden sets in v1 (edit by hand).

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
