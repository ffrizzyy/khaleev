# Khaleev — Task Plan

## How to run these tasks

Execute the tasks **sequentially in the order listed** — each task depends only on the ones above it, and each one leaves the repo in a working, green state. For every task: read the task block, implement only the files it names, run its `Verify` command(s) to completion (all must pass), then make **one commit** scoped to that task (e.g. `feat(chunking): chunk pages with page attribution`) and **one push** of that commit. Do not start the next task until the current one is committed and pushed. Every task already contains its own tests, so there is no separate "write the tests" task — tests are part of the acceptance criteria of the task they belong to. No task may require a running Ollama instance, an API key, or any network access to pass its `Verify` command; model-backed paths are always exercised through injected fakes (fake embedder, fake generator, fake entailment scorer) or `httpx.MockTransport`. Runtime dependencies introduced along the way (`pypdf`, `faiss-cpu`, `sentence-transformers`, `alembic`, `httpx`, `pydantic-settings`, `react-router-dom`, `vitest`, …) are called out in the task that introduces them because SPEC's `## Boundaries → Ask first` requires the user to approve new runtime dependencies before they are added.

## Tasks

- [x] T01 — Scaffold backend and frontend toolchains with an offline test guard
  - Depends on: none
  - Files: `backend/pyproject.toml`, `backend/src/khaleev/__init__.py`, `backend/src/khaleev/paths.py`, `backend/tests/conftest.py`, `backend/tests/unit/test_smoke.py`, `backend/.env.example`, `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/tsconfig.node.json`, `frontend/index.html`, `frontend/eslint.config.js`, `frontend/.prettierrc.json`, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/test/setup.ts`, `frontend/src/__tests__/App.test.tsx`, `docs/references/.gitkeep`
  - Acceptance: `backend` is a `uv` project (Python >= 3.11, ruff line-length 100, pytest configured, `src` layout with the `khaleev` package importable via `uv sync`); `frontend` is a Vite + React + TypeScript project with `strict: true` and a `/api` dev proxy to `http://localhost:8000`; `backend/tests/conftest.py` installs an autouse socket guard that raises on any outbound socket connect so no test can reach the network (AC8, Locked intent #12); a smoke test and a trivial RTL render test exist so `pytest` and `vitest` both exit 0 with no network. Runtime deps introduced: none beyond the toolchains themselves.
  - Verify: `cd backend && uv sync && uv run ruff check . && uv run pytest -q` then `cd frontend && npm install && npm run lint && npm run build && npm test -- --run`

- [x] T02 — Add the settings module and the local data directory layout
  - Depends on: T01
  - Files: `backend/src/khaleev/config.py`, `backend/src/khaleev/paths.py`, `backend/tests/conftest.py`, `backend/tests/unit/test_config.py`, `backend/.env.example`
  - Acceptance: `Settings` exposes `data_dir`, `embedder_id` (default `all-MiniLM-L6-v2`, suggestion), `generator` (default `ollama`), `ollama_base_url`, `ollama_model` (default `llama3.1:8b`, suggestion), optional `cloud_api_key`/`cloud_model`, `retrieval_k` (default 5), `chunk_size` (default 600, validated within 400–800) and `chunk_overlap_ratio` (default 0.12, validated within 0.10–0.15), `golden_dir`; `Settings()` constructs with **no** environment variables set and no required API key (AC3, Locked intent #11); `ensure_data_dir()` creates `pdfs/`, `index/`, `golden/` under the data dir idempotently and returns the resolved paths; every test resolves the data dir to `tmp_path` so nothing writes to the user's real data directory (Boundaries → Never).
  - Verify: `cd backend && uv run ruff check . && uv run pytest tests/unit/test_config.py -q`

- [x] T03 — Define the SQLAlchemy models and the initial Alembic migration
  - Depends on: T02
  - Files: `backend/src/khaleev/db.py`, `backend/src/khaleev/models/__init__.py`, `backend/src/khaleev/models/base.py`, `backend/src/khaleev/models/document.py`, `backend/src/khaleev/models/chunk.py`, `backend/src/khaleev/models/golden.py`, `backend/src/khaleev/models/eval_run.py`, `backend/alembic.ini`, `backend/src/khaleev/migrations/env.py`, `backend/src/khaleev/migrations/versions/0001_initial.py`, `backend/tests/unit/test_models.py`, `backend/tests/unit/test_migrations.py`
  - Acceptance: tables `documents`, `chunks`, `golden_sets`, `eval_runs`, `eval_run_entries` exist with exactly the columns listed in SPEC's data model (`documents.content_hash` UNIQUE; `chunks` carries `document_id`, `page_number`, `chunk_index`, `text`, `embedding_ref`; `eval_runs` carries `k`, `embedder_id`, `scorer_id`, `hit_rate`, `faithfulness`, `config` JSON; `eval_run_entries` carries `golden_index`, `hit`, `answer`, `claims`, `supported_claims`, `faithfulness`); deleting a document cascades to chunks, golden sets, eval runs and eval run entries; `alembic upgrade head` against a temp SQLite file yields the same tables/columns as the ORM metadata, so the first migration is the only schema change ever needed (risk flag: this is the one-way door for the schema — SPEC `## Boundaries → Ask first` applies to any later change).
  - Verify: `cd backend && uv run ruff check . && uv run pytest tests/unit/test_models.py tests/unit/test_migrations.py -q`

- [x] T04 — Ingest PDFs with content-hash dedupe and per-page extraction
  - Depends on: T03
  - Files: `backend/src/khaleev/ingest/__init__.py`, `backend/src/khaleev/ingest/pdf.py`, `backend/src/khaleev/ingest/pipeline.py`, `backend/src/khaleev/services/documents.py`, `backend/tests/fixtures/pdf_factory.py`, `backend/tests/unit/test_pdf_extract.py`, `backend/tests/integration/test_document_upload.py`
  - Acceptance: `extract_pages(pdf_bytes)` returns one `PageText` per PDF page in the PDF's own order with 1-based page numbers (assumption A1) and the correct page count; uploading a fixture multi-page PDF stores the original bytes under `<data_dir>/pdfs/<content_hash>.pdf` and creates one `documents` row with `content_hash`, `title` and `page_count`; uploading the identical bytes again returns the existing document id and creates no second row (AC1, F1); the test fixture builds a real multi-page PDF in-repo from raw PDF bytes so no extra test dependency and no download are needed (assumption A6).
  - Verify: `cd backend && uv run ruff check . && uv run pytest tests/unit/test_pdf_extract.py tests/integration/test_document_upload.py -q`

- [x] T05 — Chunk each page while preserving page attribution
  - Depends on: T04
  - Files: `backend/src/khaleev/ingest/chunking.py`, `backend/src/khaleev/ingest/pipeline.py`, `backend/tests/unit/test_chunking.py`
  - Acceptance: `chunk_page(page_number, text)` returns chunks that each carry the source `page_number`, a sequential `chunk_index` starting at 0, and text within the configured size bound (only the last chunk of a page may be shorter) (Locked intent #2); consecutive chunks overlap by the configured ratio and, after stripping the overlap prefix from every chunk after the first, the chunks reassemble exactly into the original page text so no content is dropped; chunking never emits an empty chunk; the ingest pipeline persists chunks with `(document_id, page_number, chunk_index, text)` and a placeholder `embedding_ref` (suggestion: 400–800 char chunks with 10–15% overlap).
  - Verify: `cd backend && uv run ruff check . && uv run pytest tests/unit/test_chunking.py -q`

- [x] T06 — Add local embeddings and a file-backed vector index
  - Depends on: T05
  - Files: `backend/src/khaleev/ingest/embedding.py`, `backend/src/khaleev/retrieval/index.py`, `backend/src/khaleev/ingest/pipeline.py`, `backend/tests/unit/test_embedding.py`, `backend/tests/unit/test_index.py`
  - Acceptance: an `Embedder` protocol exposes `embed_texts(list[str]) -> list[list[float]]` and `embed_query(str) -> list[float]`; the `SentenceTransformerEmbedder` implementation imports `sentence_transformers` lazily and only at call time so tests never load a model, and `FakeEmbedder` (deterministic, seeded from the text) is the only embedder used in tests (Locked intent #12); `VectorIndex` wraps a local FAISS inner-product index stored at `<data_dir>/index/<document_id>.faiss` and supports add, `search_top_k`, `delete_document` and reload-from-disk, with vector ids mapped back to `chunks.embedding_ref`; the ingest pipeline embeds the chunks and writes their vectors to the index (suggestion: `all-MiniLM-L6-v2` + FAISS local file index).
  - Verify: `cd backend && uv run ruff check . && uv run pytest tests/unit/test_embedding.py tests/unit/test_index.py -q`

- [x] T07 — Implement document-scoped top-k retrieval
  - Depends on: T06
  - Files: `backend/src/khaleev/retrieval/search.py`, `backend/tests/unit/test_retrieval.py`
  - Acceptance: `retrieve(document_id, question, k)` returns `min(k, n)` chunks ordered by descending similarity score, each carrying `chunk_id`, `page_number`, `chunk_index`, `text` and `score`; no result ever belongs to another document and no result has a missing page number (Boundaries → Always); `k` defaults to the configured 5 and can be overridden per call, and the same `k` value is what gets recorded with an eval run so hit-rate@k stays comparable across runs (suggestion: default k=5).
  - Verify: `cd backend && uv run ruff check . && uv run pytest tests/unit/test_retrieval.py -q`

- [x] T08 — Add the generator abstraction, the Ollama client, and citation validation
  - Depends on: T07
  - Files: `backend/src/khaleev/generation/__init__.py`, `backend/src/khaleev/generation/base.py`, `backend/src/khaleev/generation/prompts.py`, `backend/src/khaleev/generation/ollama.py`, `backend/src/khaleev/generation/cloud.py`, `backend/src/khaleev/generation/citations.py`, `backend/src/khaleev/api/schemas.py`, `backend/tests/unit/test_citations.py`, `backend/tests/unit/test_ollama_client.py`, `backend/tests/unit/test_cloud_client.py`
  - Acceptance: a `Generator` protocol exposes `generate(prompt: str) -> str`; `OllamaGenerator` posts to `{ollama_base_url}/api/generate` through `httpx` and `CloudGenerator` exists but is only selectable when a cloud key is configured — it is never the default and the app stays fully usable with zero keys (Locked intent #10, #11, AC3); the prompt supplies the retrieved chunks with their page numbers and requires page-tagged citations; `parse_citations(answer, retrieved)` returns structured `[{page, quote}]`, drops any cited page that is not among the retrieved chunk pages, dedupes by page, and returns a non-empty list by falling back to the retrieved pages when the generator emitted no citation at all, so an answer can never ship without citations (Locked intent #4, assumption A2, Boundaries → Never); all generator tests use a `FakeGenerator` and `httpx.MockTransport`, so no socket is opened and the suite-wide socket guard proves it.
  - Verify: `cd backend && uv run ruff check . && uv run pytest tests/unit/test_citations.py tests/unit/test_ollama_client.py tests/unit/test_cloud_client.py -q`

- [x] T09 — Expose the document library, ask, and config API routes
  - Depends on: T08
  - Files: `backend/src/khaleev/app.py`, `backend/src/khaleev/api/__init__.py`, `backend/src/khaleev/api/deps.py`, `backend/src/khaleev/api/schemas.py`, `backend/src/khaleev/api/routes/__init__.py`, `backend/src/khaleev/api/routes/documents.py`, `backend/src/khaleev/api/routes/ask.py`, `backend/src/khaleev/api/routes/config.py`, `backend/src/khaleev/services/qa.py`, `backend/src/khaleev/services/documents.py`, `backend/tests/integration/test_documents_api.py`, `backend/tests/integration/test_ask_api.py`
  - Acceptance: `POST /api/documents` (multipart) returns 201 with `{id, title, page_count}` for a new file and 200 with the existing id for a duplicate content hash (AC1); `GET /api/documents` lists documents, `GET /api/documents/{id}` returns detail, and `GET /api/documents/{id}/pages/{n}` returns non-empty extracted text whose stored chunks all carry `page_number == n` (AC1); `DELETE /api/documents/{id}` removes the document row, its chunks, golden set, eval runs and entries, the vector-index file, the stored PDF and the golden-set file, and the document disappears from `GET /api/documents` (AC11); `POST /api/documents/{id}/ask` returns `{answer, citations}` with a non-empty citation list whose every `page` is a valid 1-based page of that document and whose every page came from the retrieved context (AC2, Locked intent #3); `GET /api/config` / `PUT /api/config` expose k, embedder and generator choice; every route returns a typed Pydantic model, and the integration tests run against a temp data dir with `FakeEmbedder` + `FakeGenerator` and no network (AC8).
  - Verify: `cd backend && uv run ruff check . && uv run pytest tests/integration/test_documents_api.py tests/integration/test_ask_api.py -q`

- [x] T10 — Scaffold the React app and the typed API client
  - Depends on: T09
  - Files: `frontend/src/types/index.ts`, `frontend/src/api/client.ts`, `frontend/src/api/documents.ts`, `frontend/src/api/evals.ts`, `frontend/src/api/config.ts`, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/routes.tsx`, `frontend/src/test/setup.ts`, `frontend/vite.config.ts`, `frontend/src/api/__tests__/client.test.ts`
  - Acceptance: `frontend/src/types/index.ts` mirrors the backend Pydantic models one-for-one (`Document`, `DocumentDetail`, `PageText`, `Citation`, `AskResponse`, `GoldenEntry`, `GoldenSet`, `EvalRun`, `EvalRunEntry`, `AppConfig`) so the REST contract is identical on both sides (Stack → Code style); `api/client.ts` wraps `fetch` with a base URL, JSON encoding and typed error handling, and is unit-tested with a mocked `fetch` so no request leaves the process; `api/documents.ts`, `api/evals.ts` and `api/config.ts` expose one typed function per endpoint in the SPEC API surface; the app shell renders the three routes (`/`, `/chat`, `/evals`) and `npm run build` type-checks under `strict`.
  - Verify: `cd frontend && npm run lint && npm run build && npm test -- --run`

- [x] T11 — Build the upload and document library UI
  - Depends on: T10
  - Files: `frontend/src/components/Upload.tsx`, `frontend/src/components/DocumentList.tsx`, `frontend/src/pages/Library.tsx`, `frontend/src/state/selectedDocument.ts`, `frontend/src/components/__tests__/Upload.test.tsx`, `frontend/src/components/__tests__/DocumentList.test.tsx`, `frontend/src/pages/__tests__/Library.test.tsx`
  - Acceptance: the Library page renders a file input that posts multipart to `/api/documents`, reports upload success/failure and refreshes the list without a manual reload; each listed document shows title, page count and ingest date (F2); clicking a document makes it the selected Q&A target for the Chat page through shared selection state (Locked intent #3); the delete control calls `DELETE /api/documents/{id}` and removes the row from the list (AC11); the UI shows no key-related errors or key prompts anywhere (AC3); all component tests mock the API module, so no request leaves the process.
  - Verify: `cd frontend && npm run lint && npm run build && npm test -- --run src/components src/pages`

- [x] T12 — Build the chat UI with clickable citations and the page viewer
  - Depends on: T11
  - Files: `frontend/src/pages/Chat.tsx`, `frontend/src/components/AskPanel.tsx`, `frontend/src/components/CitationList.tsx`, `frontend/src/components/PageViewer.tsx`, `frontend/src/components/__tests__/AskPanel.test.tsx`, `frontend/src/components/__tests__/CitationList.test.tsx`, `frontend/src/pages/__tests__/Chat.test.tsx`
  - Acceptance: `AskPanel` posts the question to `/api/documents/{id}/ask` and renders the answer text plus one citation chip per citation labelled with its page number (AC2); clicking a citation chip opens `PageViewer` at that page, which fetches `/api/documents/{id}/pages/{n}` and shows that page's extracted text, and refuses to open a page outside the document's page range (AC2, Boundaries → Never); when the API returns an answer with no citations the UI renders an explicit defect state instead of a bare answer (Locked intent #4); the selected document is visible in the chat header so the user can confirm which document is being questioned; all tests mock the API module.
  - Verify: `cd frontend && npm run lint && npm run build && npm test -- --run src/components src/pages`

- [x] T13 — Load and validate the per-document golden set
  - Depends on: T12
  - Files: `backend/src/khaleev/evals/__init__.py`, `backend/src/khaleev/evals/golden.py`, `backend/src/khaleev/services/documents.py`, `backend/tests/unit/test_golden.py`, `backend/tests/fixtures/golden_sample.json`
  - Acceptance: `load_golden_set(data_dir, document_id)` reads `<data_dir>/golden/<document_id>.json` and validates every entry has a non-empty `question`, a non-empty `expected_answer` and a non-empty list of integers >= 1 in `expected_pages`, raising a clear error that names the offending entry index (F4, Locked intent #8); the golden-set revision is a content hash of the file bytes, so editing the file by hand yields a new revision that eval runs can compare against (AC10); uploading a document seeds an empty golden file so the path always exists and a revision can always be recorded; the sample fixture contains at least 3 valid entries (AC4).
  - Verify: `cd backend && uv run ruff check . && uv run pytest tests/unit/test_golden.py -q`

- [x] T14 — Implement the hit rate@k metric and the half-up rounding helper
  - Depends on: T13
  - Files: `backend/src/khaleev/evals/metrics/__init__.py`, `backend/src/khaleev/evals/metrics/rounding.py`, `backend/src/khaleev/evals/metrics/hit_rate.py`, `backend/tests/unit/test_rounding.py`, `backend/tests/unit/test_hit_rate.py`
  - Acceptance: `entry_hit(expected_pages, retrieved)` is true iff at least one retrieved chunk has `page_number` in the expected set — page-level matching, independent of which part of the page a chunk came from (Metric definitions, AC7); `hit_rate(entries, k)` returns `hits / #entries` and raises a clear "metric undefined" error for an empty golden set so the run can be rejected; both values are rounded half-up to 4 decimals using `Decimal` (7/10 → `0.7000`, 2/3 → `0.6667`, not Python's banker's rounding); the worked example from SPEC is asserted as a test — expected page `[4]` against retrieved pages `[4, 4, 3, 4, 9]` hits, and a retrieved list with no expected page misses (AC7); the module imports only the standard library, so the unit tests load no model and touch no network (Locked intent #12).
  - Verify: `cd backend && uv run ruff check . && uv run pytest tests/unit/test_hit_rate.py tests/unit/test_rounding.py -q`

- [x] T15 — Implement the faithfulness metric, claim splitting, and the local entailment scorer
  - Depends on: T14
  - Files: `backend/src/khaleev/evals/metrics/faithfulness.py`, `backend/src/khaleev/evals/claims.py`, `backend/src/khaleev/evals/scorer.py`, `backend/tests/unit/test_faithfulness.py`, `backend/tests/unit/test_claims.py`, `backend/tests/unit/test_scorer.py`
  - Acceptance: `split_claims(answer)` splits an answer into sentence-level claims and drops empty or whitespace-only sentences (Metric definitions); `faithfulness(entry_results)` equals total supported claims over total claims, rounded half-up to 4 decimals, and an answer with zero claims scores `0.0` rather than raising or dividing by zero; the scorer is an injectable `EntailmentScorer` protocol (`supported(claim, context) -> bool`) and the metric tests use constructed scorer outputs only — no model is loaded and no network call is made (AC7, Locked intent #12); the scorer reports its id and version so both can be persisted with the run and scores are only comparable within the same scorer; the worked example is asserted — 15 supported of 20 claims → `0.7500`, and a single supported claim → entry faithfulness `1.0`; the default local scorer uses a local entailment model only when it is already present in the local cache (`local_files_only=True`) and otherwise falls back to keyword overlap, so it never triggers an implicit download (suggestion: local NLI cross-encoder with keyword-overlap fallback; assumption A3 — the fallback path is unit-tested with plain strings and the model path is unit-tested with an injected fake model).
  - Verify: `cd backend && uv run ruff check . && uv run pytest tests/unit/test_faithfulness.py tests/unit/test_claims.py tests/unit/test_scorer.py -q`

- [x] T16 — Persist eval runs with per-entry results and aggregate metrics
  - Depends on: T15
  - Files: `backend/src/khaleev/evals/runner.py`, `backend/src/khaleev/services/evals.py`, `backend/src/khaleev/models/eval_run.py`, `backend/tests/unit/test_runner.py`, `backend/tests/integration/test_eval_persistence.py`
  - Acceptance: `run_eval(document_id, k)` walks every golden entry — retrieve top-k chunks (hit), generate an answer, split claims, score claims — and writes one `eval_runs` row plus one `eval_run_entries` row per entry carrying `golden_index`, `hit`, `answer`, `claims`, `supported_claims` and per-entry `faithfulness` (F5, AC5); the run row persists `created_at`, `k`, `embedder_id`, `scorer_id`, `hit_rate` and `faithfulness`, both floats in `[0.0, 1.0]` and rounded half-up to 4 decimals, plus a `config` JSON holding the golden-set revision and the scorer version so runs stay comparable (AC10, Boundaries → Always); an empty golden set is rejected with a clear error and no run row is written; the runner accepts injected embedder, generator and scorer, so the tests use fakes and the suite-wide socket guard proves no network access (AC8).
  - Verify: `cd backend && uv run ruff check . && uv run pytest tests/unit/test_runner.py tests/integration/test_eval_persistence.py -q`

- [x] T17 — Expose the eval API and compute comparability flags from persisted config
  - Depends on: T16
  - Files: `backend/src/khaleev/api/routes/evals.py`, `backend/src/khaleev/evals/comparability.py`, `backend/src/khaleev/api/schemas.py`, `backend/tests/unit/test_comparability.py`, `backend/tests/integration/test_evals_api.py`
  - Acceptance: `POST /api/documents/{id}/evals` starts a run with `k` configurable and defaulting to 5 and returns the persisted run id and both metrics (AC5, F5); `GET /api/evals/{run_id}` returns the run with its per-entry results (AC5); `GET /api/documents/{id}/evals` returns the chronological history of runs with metrics and timestamps (AC6); each history row carries a `comparable` / `flagged` field computed **only** from the persisted `config` columns (golden-set revision, k, embedder id, scorer id), so a run made with `k = 10` after a run with `k = 5` is flagged instead of silently charted alongside it (AC10, Metric definitions → History comparability); `GET /api/documents/{id}/golden` returns the golden set read-only (F4, AC4); tests use fake generator, embedder and scorer and touch no network.
  - Verify: `cd backend && uv run ruff check . && uv run pytest tests/unit/test_comparability.py tests/integration/test_evals_api.py -q`

- [x] T18 — Build the eval dashboard UI
  - Depends on: T17
  - Files: `frontend/src/pages/EvalDashboard.tsx`, `frontend/src/components/EvalRunCard.tsx`, `frontend/src/components/EvalHistoryList.tsx`, `frontend/src/components/GoldenSetView.tsx`, `frontend/src/pages/__tests__/EvalDashboard.test.tsx`, `frontend/src/components/__tests__/EvalHistoryList.test.tsx`, `frontend/src/components/__tests__/GoldenSetView.test.tsx`
  - Acceptance: the dashboard shows the latest run's `hit_rate@k` and `faithfulness` formatted to 4 decimals (AC6); the history list shows every past run with its two metrics and timestamp in chronological order — a list with values, not charts, in v1 (assumption A4); runs whose persisted config differs from the latest run are visibly flagged as not comparable rather than presented as directly comparable (AC10); the selected document's golden set is displayed read-only with its question, expected answer and expected pages (AC4); a "Run eval" control posts to `/api/documents/{id}/evals` with a `k` input defaulting to 5 and then refreshes the dashboard; all tests mock the API module.
  - Verify: `cd frontend && npm run lint && npm run build && npm test -- --run src/pages src/components`

- [ ] T19 — Write the README and developer documentation
  - Depends on: T18
  - Files: `README.md`, `docs/architecture.md`, `docs/references/README.md`
  - Acceptance: the README documents the zero-key local setup (`uv sync`, `npm install`, the explicit first-run model download and `ollama pull` steps), the exact commands from SPEC (`uv run uvicorn khaleev.app:app --reload --port 8000`, `npm run dev`, `npm run build`, `uv run pytest`, `npm test`, `uv run ruff check .`, `npm run lint`) and the data directory layout (Stack → Commands); it documents the metric contracts (page-level hit rule, faithfulness denominator, half-up 4-decimal rounding, comparability rule) and the promise that the test suite never reaches the network; it contains the optional manual end-to-end check against a real Ollama instance, clearly labelled manual and explicitly excluded from CI (Stack → Testing strategy level 3, AC8); it lists every runtime dependency that was added so the user can approve them under SPEC's `## Boundaries → Ask first` rule.
  - Verify: `cd backend && uv run pytest -q` then `cd frontend && npm run build && npm test -- --run` (manual check: the README mentions `uv run uvicorn khaleev.app:app --reload --port 8000`, `uv run pytest` and `npm test`)

- [ ] T20 — Close the loop with an offline end-to-end test and final polish
  - Depends on: T19
  - Files: `backend/tests/integration/test_end_to_end.py`, `backend/tests/conftest.py`, `backend/tests/unit/test_no_network.py`, `backend/src/khaleev/app.py`, `frontend/src/App.tsx`
  - Acceptance: one integration test walks the whole user journey with fakes — upload a fixture PDF, ask a question and receive a page-cited answer, run an eval on that document, and read back both metrics plus a two-run history where the second run (with a different `k`) is flagged as not comparable (AC9, AC10); a dedicated test asserts that the suite-wide socket guard is active, so `uv run pytest` passes with all outbound connections blocked, proving the offline guarantee (AC8); `uv run ruff check .`, `npm run lint`, `npm run build` and both test suites are green in one pass, and the manual Ollama path remains optional and documented rather than automated (AC3).
  - Verify: `cd backend && uv run ruff check . && uv run pytest -q` then `cd frontend && npm run lint && npm run build && npm test -- --run`

## Risks and flags

| Risk | Impact | Mitigation |
| --- | --- | --- |
| New runtime dependencies (`pypdf`, `faiss-cpu`, `sentence-transformers`, `alembic`, `httpx`, `pydantic-settings`, `react-router-dom`, `vitest`) | SPEC says "ask first" before adding runtime dependencies | Each dependency is named in the task that introduces it (T01, T04, T06, T08, T13) so the user can approve before implementation begins |
| First migration is a one-way door for the SQLite schema | High — SPEC forbids schema changes after the first migration without asking | T03 builds the full schema in one migration and tests metadata/migration parity before anything depends on it |
| First-run model downloads (embedding model, entailment model, `ollama pull`) | Medium — violates the offline rule if done implicitly | Embedding and entailment loaders use `local_files_only`/cache-only behaviour; the download is an explicit documented setup step in T19; no test loads a model |
| `faiss-cpu` has no wheels on some platforms | Medium — blocks install | T06 keeps the index behind a small `VectorIndex` interface so a pure-NumPy fallback can be substituted without touching callers; decide during T06 |
| Early tasks are backend-heavy while the metric work lands later in the order | Low — metric tasks are pure and independently testable | T14 and T15 are dependency-free pure modules with constructed-input unit tests, satisfying the "testable independently" constraint regardless of position |

## Assumptions and suggestions used

- **Assumption A1** (1-based page numbers) → T04. **A2** (citation validation/repair) → T08. **A3** (local entailment scorer accepted) → T15. **A4** (history is a chronological list, not charts) → T18. **A5/A6** (machine capability and first-run downloads permitted) → T19, T20.
- **Suggestion** chunk size 400–800 chars with 10–15% overlap → T05. **Suggestion** `all-MiniLM-L6-v2` embedder → T02, T06. **Suggestion** FAISS local index → T06. **Suggestion** default k=5 → T02, T07, T17. **Suggestion** `llama3.1:8b` via Ollama → T02, T08. **Suggestion** NLI cross-encoder with keyword-overlap fallback → T15. **Suggestion** golden set as hand-edited JSON per document → T13.

## Traceability

| Acceptance criterion | Tasks |
| --- | --- |
| AC1 — Upload & ingest with content-hash dedupe | T04, T05, T09 |
| AC2 — Q&A with citations, clickable page references | T08, T09, T12 |
| AC3 — Zero-key operation | T02, T08, T09, T19, T20 |
| AC4 — Golden set loads and is visible in the UI | T13, T17, T18 |
| AC5 — Eval run produces both metrics, persisted | T14, T15, T16, T17 |
| AC6 — Dashboard shows latest metrics plus run history | T16, T17, T18 |
| AC7 — Metric unit tests (hit rate, faithfulness denominator/rounding) | T14, T15 |
| AC8 — Offline test suite | T01, T02, T08, T09, T16, T17, T19, T20 |
| AC9 — End-to-end journey | T20 |
| AC10 — Run comparability flagged from persisted config | T13, T16, T17, T18, T20 |
| AC11 — Delete is complete | T09, T11, T20 |
