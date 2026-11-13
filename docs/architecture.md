# Khaleev architecture

This document describes what is actually built in this repository: the processes, the module map,
the three request flows, the persistence model, and the exact places where the citation guarantee
is enforced. It is written from the code, not from the intent; where something is missing, it says
so and links to the README's [Known gaps](../README.md#known-gaps).

Related documents: `SPEC.md` (requirements and locked intent), `tasks/plan.md` (the task history),
[README.md](../README.md) (setup, commands, metric contracts), [references/README.md](references/README.md)
(future reference material).

---

## 1. Constraints that shaped the design

1. **Single user, single machine, local only.** One SQLite file, PDF originals on disk, one FAISS
   file per document, golden sets as JSON files. No accounts, no auth, no multi-tenancy, no cloud
   storage.
2. **Zero required API keys.** Ollama is the default generator; embeddings and the entailment
   judge run locally. Cloud generation exists but is never the default and requires an explicit
   `KHALEEV_GENERATOR=cloud` plus a key and model.
3. **Every chunk and every citation carries a 1-based page number.** A chunk without a page, or an
   answer without citations, is a defect — not a degraded result.
4. **The test suite never touches the network.** Every model-backed dependency sits behind a small
   protocol and is injected; an autouse socket guard proves it.
5. **Eval runs are persisted, never computed only in memory**, and each run records the config its
   metrics are comparable under.

## 2. Runtime shape

Two processes in development, one origin from the browser's point of view:

```text
browser ──▶ Vite dev server :5173 ──▶ proxy /api ──▶ FastAPI (uvicorn) :8000
                     │                                     │
                     └── serves the React app              ├── SQLite  <data_dir>/khaleev.db
                                                           ├── PDFs    <data_dir>/pdfs/*.pdf
                                                           ├── FAISS   <data_dir>/index/*.faiss
                                                           ├── golden  <data_dir>/golden/*.json
                                                           └── Ollama  http://localhost:11434
```

- `frontend/vite.config.ts` proxies `/api` to `http://localhost:8000`; `frontend/src/api/client.ts`
  always calls the relative `/api` base, so the same client code works behind the proxy.
- The backend exposes `/api` only — it does not mount `frontend/dist`, and no CORS middleware is
  configured. The Vite dev proxy is the supported UI path in v1; this is a deliberate limitation,
  described in section 11.
- `create_app()` in `backend/src/khaleev/app.py` is the only constructor. It takes
  `settings`, `embedder`, `generator`, `scorer` as optional arguments; production calls it with none
  and the real implementations are built lazily. `app = create_app()` at module level is what
  uvicorn imports (`khaleev.app:app`).
- `AppServices` (`backend/src/khaleev/api/deps.py`) holds the per-process container on
  `app.state.services`: the SQLite engine (opened on first use), the embedder, the generator and the
  scorer (each built on first use).
- The lifespan hook applies the app's Alembic migrations to the configured data directory before
  serving (`khaleev.migrations.apply_startup_migrations`) and disposes the engine on shutdown.
  Importing the app creates no directory, runs no migration, loads no model and opens no socket.

## 3. Module map

### Backend — `backend/src/khaleev/`

| Path | Responsibility |
| --- | --- |
| `app.py` | `create_app()` factory, router mounting, and the **single** mapping of domain errors to HTTP status codes. Module-level `app`. |
| `config.py` | `Settings` (pydantic-settings, `KHALEEV_*` env / `.env`), all local defaults, `ensure_data_dir()`. |
| `paths.py` | `DataPaths` and the `pdfs/`, `index/`, `golden/` layout under the data directory. Pure path derivation; creates nothing on import. |
| `db.py` | SQLite engine, session factory, `PRAGMA foreign_keys=ON` per connection, `database_path()`. |
| `models/` | SQLAlchemy ORM: `document.py`, `chunk.py`, `golden.py`, `eval_run.py` (`EvalRun`, `EvalRunEntry`), `base.py`. |
| `migrations/` | Alembic environment (`env.py`, resolving the DB from `Settings.data_dir`) and `versions/0001_initial.py`. |
| `migrations.py` | `apply_startup_migrations()` — applies `alembic upgrade head` to the configured data dir on every boot, idempotently and on the CLI's history. |
| `api/deps.py` | `AppServices` container and the FastAPI dependency providers (`SessionDep`, `EmbedderDep`, `GeneratorDep`, `ScorerDep`, `ServicesDep`). |
| `api/schemas.py` | The typed REST contract shared with the frontend: documents, ask, config, golden set, eval runs. |
| `api/routes/documents.py` | Upload, list, detail, page text, golden set, delete. |
| `api/routes/ask.py` | `POST /api/documents/{id}/ask`. |
| `api/routes/config.py` | `GET` / `PUT /api/config`. |
| `api/routes/evals.py` | Start a run, read a run, read history with comparability flags. |
| `services/documents.py` | Upload use case, list/get/delete, page-text reconstruction, golden-set read. |
| `services/qa.py` | The whole ask use case: retrieve → prompt → generate → validate citations. No web imports. |
| `services/evals.py` | Persist one eval run atomically (`run_eval`, `persist_eval_run`), read a run, list history. |
| `ingest/pdf.py` | `extract_pages()` — per-page text with 1-based page numbers; `NotAPdfError`, `CorruptPdfError`. |
| `ingest/chunking.py` | `chunk_page()` / `chunk_pages()` — overlapping, page-bounded chunks with `(page_number, chunk_index)`. |
| `ingest/embedding.py` | `Embedder` protocol, lazy `SentenceTransformerEmbedder`, deterministic `FakeEmbedder`, `l2_normalize`. |
| `ingest/pipeline.py` | `ingest_pdf()` — content-hash dedupe, stored PDF, chunk rows, embedding + index write. |
| `retrieval/index.py` | `VectorIndex` — one FAISS `IndexIDMap2(IndexFlatIP)` file per document; add, search, delete, reload. |
| `retrieval/search.py` | `retrieve()` — document-scoped top-k, index→chunk join, page validation, effective-`k` recording. |
| `generation/base.py` | `Generator` protocol, `GenerationError`, `GeneratorNotConfiguredError`, `FakeGenerator`. |
| `generation/prompts.py` | `build_prompt()` and `CITATION_INSTRUCTION` — page-labelled excerpts, page-tag requirement. |
| `generation/ollama.py` | `OllamaGenerator` — one POST to `{base_url}/api/generate`, `stream: false`, actionable errors. |
| `generation/cloud.py` | `CloudGenerator` — OpenAI-compatible chat-completions client; opt-in only. |
| `generation/__init__.py` | `build_generator()` — the single place the configured generator is chosen. |
| `generation/citations.py` | `parse_citations()` — the citation repair layer (validation, dedupe, verbatim quotes, fallback). |
| `evals/golden.py` | Golden-set file path, strict validation, SHA-256 revision, seed/persist/sync. |
| `evals/claims.py` | `split_claims()` — one claim per sentence, page tags removed, fragments dropped. |
| `evals/scorer.py` | `EntailmentScorer` protocol, `LocalEntailmentScorer` (NLI with `local_files_only=True`, lexical fallback), `LexicalOverlapScorer`, `FakeEntailmentScorer`, `select_context()`. |
| `evals/metrics/rounding.py` | `round_half_up()`, `format_metric()` — `Decimal`, `ROUND_HALF_UP`, 4 places. |
| `evals/metrics/hit_rate.py` | `entry_hit()`, `hit_rate()`, `MetricUndefinedError`. |
| `evals/metrics/faithfulness.py` | `score_answer()`, `faithfulness()`, `FaithfulnessEntry`, `entry_faithfulness()`. |
| `evals/runner.py` | `evaluate()` — orchestration over injected dependencies; builds `EvalReport` and its `config`; persists nothing. |
| `evals/comparability.py` | `compare_runs()`, `run_signature()` — reads only persisted rows; flags older runs that differ from the newest. |

### Frontend — `frontend/src/`

| Path | Responsibility |
| --- | --- |
| `main.tsx`, `App.tsx`, `routes.tsx` | App shell and the three routes: `/` Library, `/chat` Chat, `/evals` Eval dashboard. |
| `api/client.ts` | The one `fetch` wrapper: `/api` base URL, JSON/multipart bodies, typed `ApiError`. |
| `api/documents.ts`, `api/evals.ts`, `api/config.ts` | One typed function per backend endpoint. |
| `types/index.ts` | TypeScript mirror of the backend Pydantic models. |
| `state/selectedDocument.ts` | Shared "one selected document" state across Library, Chat and the dashboard. |
| `components/Upload.tsx` | PDF upload, client-side PDF check, dedupe reporting. |
| `components/DocumentList.tsx` | Library rows: select and delete. |
| `components/AskPanel.tsx` | Ask form, answer, explicit defect state for an uncited answer. |
| `components/CitationList.tsx` | One keyboard-reachable button per source page, with its quote. |
| `components/PageViewer.tsx` | Fetches and shows one page's extracted text; refuses out-of-range pages. |
| `components/EvalRunCard.tsx`, `components/EvalHistoryList.tsx`, `components/GoldenSetView.tsx` | Latest-run metrics, run history with flags, read-only golden set. |
| `pages/Library.tsx`, `pages/Chat.tsx`, `pages/EvalDashboard.tsx` | The three page bodies. |

`frontend/src/main.tsx` mounts `App` and imports **no stylesheet**: the repository contains no CSS
file, so every component renders as browser-default HTML apart from two inline styles in
`PageViewer.tsx` (the dialog box and `pre-wrap` page text). The UI is unstyled until T20 (README
known gap 3).

## 4. Flow A — upload → ingest → chunk → embed → index

Entry point: `POST /api/documents` (multipart) → `api/routes/documents.upload_document`.

1. **Read the upload.** The route reads the file bytes and calls
   `services/documents.upload_document(session, pdf_bytes, filename, settings, embedder)`. The
   embedder is always supplied by the API (`EmbedderDep`), because an unembedded document retrieves
   nothing.
2. **Dedupe by content hash.** `ingest/pipeline.ingest_pdf` computes `content_hash()` (SHA-256) and
   looks for an existing `documents` row. If found it returns `IngestResult(created=False)` and
   touches nothing — no second row, file, chunks or vectors. The route turns that into **200**;
   a genuinely new file is **201**.
3. **Extract per page.** `ingest/pdf.extract_pages()` validates the `%PDF-` header
   (`NotAPdfError` → 400) then uses pypdf to produce one `PageText(page_number, text)` per page, in
   the PDF's own order, numbered from 1. A blank page yields `""`; no text is invented (OCR is a
   non-goal). Unreadable/encrypted PDFs raise `CorruptPdfError` → 422.
4. **Store the original.** `paths.DataPaths.from_data_dir(data_dir).create()` creates the layout
   if needed, and the bytes are written to `<data_dir>/pdfs/<content_hash>.pdf`.
5. **Create the document row.** `Document(content_hash, title, page_count)` is added and flushed so
   its primary key exists for the chunks. The title is the bare uploaded filename; a client-supplied
   path never reaches the row.
6. **Chunk each page.** `ingest/chunking.chunk_pages()` calls `chunk_page(page_number, text)` per
   page: `chunk_size` characters (default 600), stride `chunk_size - round(chunk_size * overlap)`
   (default 528, i.e. 72 characters of overlap), 0-based `chunk_index` within the page, never
   crossing a page boundary. Blank pages emit no chunks. Each chunk becomes one `chunks` row with
   `document_id`, `page_number`, `chunk_index`, `text` and a null `embedding_ref`.
7. **Embed and index.** After a flush gives the chunk rows their ids,
   `ingest/pipeline._embed_chunks()` calls `embedder.embed_texts()` once for the batch, checks the
   vector count matches, then `VectorIndex(root, document_id).add(vectors, ids)` with the chunk ids
   as FAISS ids, and writes each id back to `chunks.embedding_ref` (as text).
   `ingest/embedding.l2_normalize()` guarantees unit vectors, which is what makes the inner-product
   index return cosine similarity.
8. **Commit, then seed the golden file.** The transaction is committed, and
   `services/documents.upload_document` calls `evals/golden.seed_golden_file()`, which writes
   `[]` to `<data_dir>/golden/<document_id>.json` only if the file does not exist. The path always
   exists, so an eval can always record a revision; a hand-edited file is never overwritten.

`VectorIndex.add()` reloads the file, appends and rewrites it atomically
(`.tmp` + `replace`), so a fresh process never silently drops earlier vectors. Adding zero vectors
is a no-op.

Reading a page back (`GET /api/documents/{id}/pages/{n}`) does **not** re-parse the PDF:
`services/documents.page_text()` selects that page's chunks and `reconstruct_page_text()` reassembles
them, stripping the overlap prefix from every chunk after the first. Only chunks of the requested
page are passed in, so pages can never be joined together.

## 5. Flow B — ask → retrieve → prompt → generate → citations

Entry point: `POST /api/documents/{id}/ask` → `api/routes/ask.ask` →
`services/qa.answer_question`.

1. **Document exists.** `services/documents.get_document()` raises `DocumentNotFoundError` → 404.
   The question is stripped; an empty question is a `ValueError` (the Pydantic body already rejects
   blanks).
2. **Retrieve.** `retrieval/search.retrieve(document_id, question, k, session, embedder, settings,
   data_dir)`:
   - `resolve_k()` resolves the effective `k` (caller override or `Settings.retrieval_k`, default
     5) and rejects `k < 1`.
   - `embedder.embed_query(question)` produces the query vector.
   - `VectorIndex(data_dir, document_id).search_top_k(vector, k)` returns at most `min(k, n)`
     `(vector_id, score)` matches, highest cosine similarity first.
   - `_to_hits()` fetches the chunk rows in one query and drops, with a log line, any match whose
     row is missing (stale index), whose `document_id` differs (scope violation), or whose
     `page_number` is missing or `< 1` (attribution defect). Retrieval degrades to fewer results; it
     never raises for a stale id.
   - The result (`RetrievalResult`) carries `document_id`, the **effective `k`** and the ordered
     `RetrievedChunk`s (`chunk_id`, `page_number`, `chunk_index`, `text`, `score`).
3. **No context is a hard stop.** If `retrieved.chunks` is empty, `answer_question` raises
   `NoContextError` → 422 and the generator is **never called**. There is nothing to ground an
   answer in, so no uncited answer can be produced.
4. **Build the prompt.** `generation/prompts.build_prompt(question, chunks)` emits one excerpt per
   chunk, each introduced by `[excerpt N | chunk <id> | page <n>]`, then `CITATION_INSTRUCTION`
   ("Cite the source page of every factual claim … Never invent a page number …"). The prompt is
   pure: no settings, no I/O.
5. **Generate.** `generator.generate(prompt)` — `OllamaGenerator` POSTs
   `{base_url}/api/generate` with `stream: false` and a 120 s timeout; non-200, malformed JSON,
   empty text or an unreachable server all become `GenerationError` → 503 with an actionable
   message. `CloudGenerator` (only built when explicitly selected and configured) uses an
   OpenAI-compatible `/chat/completions` call.
6. **Validate and repair citations.** `generation/citations.parse_citations(answer, retrieved)`:
   finds page tags (`[page 3]`, `[3]`, `(p. 3)`, lists and ranges), **drops** any page that is not
   among the retrieved chunk pages, dedupes by page (first appearance wins), keeps a candidate
   quote only when the model's words occur verbatim in that page's retrieved text, otherwise uses a
   deterministic snippet, and — if no usable citation survives — cites **every retrieved page** in
   retrieval order. An empty answer, or retrieval with no chunks, raises `GenerationError`.
7. **Serialize.** `api/schemas.AnswerResponse` enforces `citations` with `min_length=1` and
   `page >= 1`, so a response that slipped through the code above would still be rejected by the
   schema rather than shipped.

The same `build_prompt` / `parse_citations` pair is used by the eval runner, so eval answers are
cited by the same code path (and a citation defect would equally fail an eval run).

## 6. Flow C — eval → retrieve → score → persist

Entry point: `POST /api/documents/{id}/evals` → `api/routes/evals.start_eval` →
`services/evals.run_eval`.

1. **Resolve the run's dependencies.** `run_eval` uses the injected embedder/generator/scorer when
   given, otherwise `build_generator(settings)` and `LocalEntailmentScorer()`.
2. **Load the golden set.** `evals/runner.evaluate()` confirms the document exists, resolves the
   effective `k` **once** (so every entry and the persisted run share it), and calls
   `_load_golden_set()`. `evals/golden.load_golden_set()` reads
   `<data_dir>/golden/<document_id>.json`, validates it strictly, and computes the revision as the
   SHA-256 of the file's exact bytes. An empty file is translated to `MetricUndefinedError` → 422
   and no run is written.
3. **Score each entry** (`runner._score_entry`), for entry index `i`:
   - `retrieve(document_id, entry.question, k, …)` — same retrieval as Flow B; empty retrieval
     raises `ValueError` (actionable: re-upload so chunks are embedded).
   - `generator.generate(build_prompt(...))` — one answer per entry.
   - `parse_citations(answer, retrieved)` — citations are built even though the metric does not
     persist them; they select the evidence below.
   - `score_answer(answer, citations, retrieved, scorer)` in `evals/metrics/faithfulness.py`:
     - `split_claims(answer)` → the claims (denominator);
     - `select_context(citations, retrieved)` → the cited pages' chunks, or all top-k chunks when
       the answer cited nothing (`scorer.evidence_chunks`);
     - `score_claims(claims, context, scorer)` → one binary verdict per claim, so
       `claims` and `supported_claims` are counts of the same list.
   - `entry_hit(entry.expected_pages, retrieved.chunks[:k])` → the page-level hit for this entry.
4. **Aggregate without re-deriving maths.** `hit_rate(hit_entries, k)` and
   `faithfulness(faithfulness_entries)` are the metric functions themselves (Flow C never reimplements
   the formulas). `EvalReport` also captures the comparability config: `k`, `embedder_id`
   (`embedder_identity`), `generator` (`generator_identity`), `scorer_id`, `scorer_version`, and the
   golden-set revision. `scorer.id` is read **after** all claims are scored, so a run that fell back
   to lexical overlap is recorded as `local-lexical-overlap` rather than as the intended NLI model.
5. **Persist atomically.** `services/evals.persist_eval_run()` writes one `eval_runs` row (metrics,
   `k`, `embedder_id`, `scorer_id`, `config` JSON) and one `eval_run_entries` row per golden entry
   (`golden_index`, `hit`, `answer`, `claims`, `supported_claims`, `faithfulness`), then
   `run_eval` commits. Any exception rolls the transaction back, so a failed run leaves no partial
   history. Runs are append-only.
6. **Read history and compare.** `GET /api/documents/{id}/evals` →
   `services/evals.list_eval_runs()` (oldest first) → `evals/comparability.compare_runs()`:
   `newest_first()` orders by `(created_at, id)`; `run_signature()` reads `k`, `embedder_id`,
   `scorer_id` from columns and `golden_set_revision` from the persisted `config` JSON. The newest
   run is the reference and is never flagged; any older run whose signature differs is returned as
   `flagged: true, comparable: false`. Live `Settings` is never consulted, so changing a setting
   after a run cannot rewrite its history.

## 7. Where the citation guarantee is enforced

Locked intent #4 says an answer without page citations is a defect; Boundaries → Never says never
ship an answer without citations or cite a page whose chunk was not in the retrieval context. Seven
layers implement that, in order:

| # | Layer | Module / function | What it guarantees |
| --- | --- | --- | --- |
| 1 | Chunking | `ingest/chunking.py` → `chunk_page` | Rejects `page_number < 1`; every chunk belongs to exactly one page and keeps its 1-based number. |
| 2 | Retrieval | `retrieval/search.py` → `_to_hits` | A chunk with no usable page is dropped, so an unciteable chunk can never reach the prompt. Foreign-document chunks are dropped too. |
| 3 | Ask ordering | `services/qa.py` → `answer_question` | Empty retrieval raises `NoContextError` before the generator is called: no context, no answer. |
| 4 | Prompt | `generation/prompts.py` → `build_prompt` | Each excerpt is labelled with its page; `CITATION_INSTRUCTION` requires a page tag per claim and forbids invented pages. |
| 5 | Repair | `generation/citations.py` → `parse_citations` | Drops pages not in the retrieved context, dedupes, verifies quotes verbatim, and falls back to one citation per retrieved page. An answer can never leave this function with zero citations. |
| 6 | Schema | `api/schemas.py` → `AnswerResponse`, `Citation` | `citations` has `min_length=1`; `page >= 1`; `quote` must be non-blank; `answer` must be non-blank. |
| 7 | UI | `frontend/src/components/AskPanel.tsx`, `CitationList.tsx`, `PageViewer.tsx` | A zero-citation response is rendered as an explicit defect state; citation chips are labelled with the page number; the viewer refuses a page outside the document's range. |

The eval path reuses layers 1, 2 and 5 (`runner._score_entry` calls `parse_citations`), which is why
a broken citation path would also fail evals rather than quietly persist a score.

## 8. Persistence model

Schema created by the single migration `migrations/versions/0001_initial.py`; the ORM mirrors it and
a parity test keeps them aligned.

| Table | Columns that matter |
| --- | --- |
| `documents` | `id`, `content_hash` (UNIQUE), `title`, `page_count`, `created_at` |
| `chunks` | `id`, `document_id` FK, `page_number`, `chunk_index`, `text`, `embedding_ref` |
| `golden_sets` | `document_id` FK (one row per document), `revision`, `path`, `entries` JSON |
| `eval_runs` | `id`, `document_id` FK, `created_at`, `k`, `embedder_id`, `scorer_id`, `hit_rate`, `faithfulness`, `config` JSON |
| `eval_run_entries` | `run_id` FK + `golden_index` (composite PK), `hit`, `answer`, `claims`, `supported_claims`, `faithfulness` |

- PDFs, the FAISS index and golden JSON live on disk; SQLite holds metadata and metrics only.
- Foreign keys are enabled per connection (`PRAGMA foreign_keys=ON` in `db.py`) and every child FK
  declares `ON DELETE CASCADE`, so deleting a document row removes chunks, the golden-set row, eval
  runs and eval entries. `services/documents.delete_document()` then explicitly unlinks the three
  artifacts no foreign key can reach: `<index>/<id>.faiss`, the stored PDF and the golden JSON.
- The golden set is file-first: the JSON is the source of truth, the `golden_sets` row is a derived
  copy kept in step on read (`sync_golden_set`), and the revision is the file's content hash.
- `config` on `eval_runs` mirrors the columns it can (`k`, `embedder_id`, `scorer_id`) and adds
  `golden_set_revision`, `scorer_version`, `generator` and `document_id`, so a later comparability
  check never has to consult anything but the row.

## 9. Error mapping

Domain errors are raised in services, runner and ingest, and mapped to HTTP exactly once in
`app.py` via `add_exception_handler`:

| Error | Status |
| --- | --- |
| `NotAPdfError` | 400 |
| `CorruptPdfError` | 422 |
| `GoldenSetNotFoundError` | 404 |
| `GoldenSetValidationError` | 422 |
| `MetricUndefinedError` | 422 |
| `NoContextError` | 422 |
| `DocumentNotFoundError`, `PageOutOfRangeError`, `EvalRunNotFoundError` | 404 |
| `GenerationError` (including `GeneratorNotConfiguredError`) | 503 |

Every body is `{"detail": "..."}` for a mapped domain error. FastAPI's own request-validation 422
keeps its standard `detail` list shape. A `RuntimeError` escaping an eval run is treated by
`api/routes/evals._run_or_unavailable` as an unavailable scorer and surfaced as the same 503 rather
than a 500.

## 10. Test seams and dependency boundaries

Each model-backed component is a runtime-checkable protocol with a deterministic fake, and the app
takes the implementation as an argument:

| Protocol | Production implementation | Test double |
| --- | --- | --- |
| `ingest/embedding.Embedder` | `SentenceTransformerEmbedder` (torch imported inside `_load_model`, first call only) | `FakeEmbedder` (SHA-256-seeded vectors) |
| `generation/base.Generator` | `OllamaGenerator` (default), `CloudGenerator` (opt-in) | `FakeGenerator`, `httpx.MockTransport` for the real clients |
| `evals/scorer.EntailmentScorer` | `LocalEntailmentScorer` (NLI cache-only, lexical fallback) | `FakeEntailmentScorer` |

Because `create_app(settings, embedder=…, generator=…, scorer=…)` injects them, integration tests
exercise the real routes and services with fakes, against a temp data directory, with no network.
The suite-wide guarantees (autouse socket guard, temp data dir) are described in the README's
[offline test guarantee](../README.md#the-offline-test-guarantee).

## 11. Deliberate v1 limitations

These are architectural choices, not defects:

- History is a chronological list with values and flags — not a chart (assumption A4).
- `k`, the embedder and the generator can be changed at runtime through `/api/config`, but a
  changed embedder does not re-embed existing documents; re-upload (or use a fresh data directory)
  and expect old runs to be flagged.
- Evals run on demand only; there is no scheduler or background worker.
- One document per question; retrieval is document-scoped by index file and cross-checked against
  `chunks.document_id`.
- No OCR: a scanned page yields empty text and therefore no chunks.

Open defects that a live run of v0.1.0 exposed are fixed: the app applies its Alembic migrations on
startup (so a fresh install needs no manual step), and `uvicorn` is a declared backend dependency.
The remaining quality gap — the frontend has no stylesheet, so the UI is unstyled — is listed with
its workaround in the README's [Known gaps](../README.md#known-gaps) and scheduled for T21. The built
frontend not being served by the API is a separate v1 limitation, described in section 2.
