# Khaleev

Khaleev is a single-user, local-first document Q&A application. You upload PDFs, ask questions
against **one selected document**, and get answers that always carry the source page numbers the
answer was drawn from. On top of that it ships an evaluation layer: a hand-curated golden Q&A set
per document, on-demand computation of retrieval hit rate and answer faithfulness, and a dashboard
that keeps every eval run with its metrics so runs can be compared.

It runs entirely on your machine: no accounts, no authentication, no cloud storage, and no API
key required. Embeddings are computed locally with `sentence-transformers`, vectors live in a local
FAISS file per document, metadata lives in a local SQLite file, and the default answer generator is
a local Ollama model.

- **Stack:** FastAPI (Python 3.11+) + SQLite + FAISS + sentence-transformers; React 19 + Vite +
  TypeScript frontend.
- **Layout:** monorepo — `backend/` (package `khaleev`) and `frontend/`.
- **Docs:** [docs/architecture.md](docs/architecture.md) explains the request flow and module map;
  [docs/references/README.md](docs/references/README.md) is the home for future reference material.
- **Status:** v0.1.0. The v1 feature set in `SPEC.md` is implemented. The database schema is
  created and migrated automatically when the API starts, so a clean `uv sync` plus the documented
  run command is all a fresh install needs. The frontend is styled with hand-written CSS (no CSS
  framework); see [Frontend styling](#frontend-styling).

---

## Contents

1. [What you can do](#what-you-can-do)
2. [Requirements](#requirements)
3. [Zero-key local setup](#zero-key-local-setup)
4. [First-run model downloads](#first-run-model-downloads)
5. [Run, test and lint commands](#run-test-and-lint-commands)
6. [Configuration](#configuration)
7. [Data directory layout](#data-directory-layout)
8. [Walkthrough: your first cited answer](#walkthrough-your-first-cited-answer)
9. [Walkthrough: your first eval run](#walkthrough-your-first-eval-run)
10. [Metric contracts](#metric-contracts)
11. [The offline test guarantee](#the-offline-test-guarantee)
12. [Manual check against a real Ollama instance](#manual-check-against-a-real-ollama-instance)
13. [Runtime dependencies added](#runtime-dependencies-added)
14. [Frontend styling](#frontend-styling)
15. [Known gaps](#known-gaps)
16. [API surface](#api-surface)

---

## What you can do

- **Upload PDFs** (multipart) into local storage. Identical bytes are deduped by content hash, so a
  re-upload returns the existing document instead of creating a duplicate.
- **Extract text per page**, keeping the 1-based page number on every chunk. A chunk never spans
  two pages.
- **Ask a question about one selected document.** The answer is generated from that document's
  retrieved chunks only, and the response always contains at least one citation
  `{page, quote}` whose page was in the retrieved context.
- **Click a citation** to open the viewer at that page and read the extracted text.
- **Maintain a golden set per document** as a hand-editable JSON file.
- **Run an eval on demand** and get two persisted metrics — retrieval hit rate @ k and answer
  faithfulness — plus one row of per-entry results.
- **Compare runs** on the dashboard. Runs produced under a different golden-set revision, `k`,
  embedding model or scorer are flagged as not comparable instead of being silently charted
  together.

Out of scope in v1: authentication/multi-user, OCR of image-only PDFs, non-PDF ingestion,
Q&A across several documents at once, automatic golden-set generation, scheduled evals, and
production hardening (TLS, rate limiting, backups).

## Requirements

- **Python 3.11+** and [uv](https://docs.astral.sh/uv/) (the backend is a uv project).
- **Node.js + npm** for the frontend (Vite 8 / TypeScript 5.9 toolchain).
- **Ollama** for answering questions with the default generator. Uploading, listing, page text,
  golden-set loading and reading history all work without it; asking a question and running an eval
  call the generator, so those need Ollama (or a configured cloud generator).
- About 8 GB of RAM is assumed (SPEC assumption A5), plus disk for the Ollama model (~5 GB for
  `llama3.1:8b`) and the embedding model (~80 MB for `all-MiniLM-L6-v2`).

No API key is required for any core feature.

## Zero-key local setup

Run the commands from the repository root unless a step says otherwise.

### 1. Install the backend (from `backend/`)

```bash
cd backend
uv sync
```

`uv sync` creates `backend/.venv` and installs the `khaleev` package in editable mode with its
dependencies.

### 2. No migration step — the schema is created on startup

There is no manual migration step. When the API starts it applies its own Alembic migrations to the
SQLite file in the data directory — creating the file and every table on a fresh install — before
serving any request. The step is idempotent: against a database already at `head` it is a no-op and
it never drops, truncates or re-seeds rows, so restarting the server is always safe.

It runs the same migration history as the CLI, so the two can never disagree about the schema.
`cd backend && uv run alembic upgrade head` still works and is useful for inspection or tooling, but
it is **not** part of setup and you never need to run it by hand.

### 3. Start the API (from `backend/`)

The SPEC command, which works after `uv sync` because `uvicorn` is a declared backend dependency:

```bash
uv run uvicorn khaleev.app:app --reload --port 8000
```

No ephemeral `--with` package overlay is needed. API docs are then at <http://localhost:8000/docs>.

### 4. Start the frontend (from `frontend/`)

```bash
cd frontend
npm install
npm run dev
```

Vite serves the UI on <http://localhost:5173> and proxies every `/api` request to
`http://localhost:8000` (configured in `frontend/vite.config.ts`). Open the UI at 5173: the API
serves `/api` only — there is no static mount of the built frontend and no CORS middleware — so the
Vite dev server is the supported UI entry point in v1. `npm run build` produces `frontend/dist/`,
but nothing serves it.

### 5. Pull the answer model (once)

With Ollama installed:

```bash
ollama serve            # if it is not already running as a service
ollama pull llama3.1:8b
```

`llama3.1:8b` is the default; change it with `KHALEEV_OLLAMA_MODEL` (see [Configuration](#configuration)).

### 6. Download the embedding model (once, explicit)

The embedding model is downloaded on the first call that embeds text — which is your first PDF
upload. To do it up front, explicitly:

```bash
cd backend
uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

Tests never trigger this download (see [The offline test guarantee](#the-offline-test-guarantee)).

## First-run model downloads

Three model-backed steps exist, and all of them are one-time setup events outside the test suite
(SPEC assumption A6):

| What | When it is fetched | Command |
| --- | --- | --- |
| Embedding model `all-MiniLM-L6-v2` | First call that embeds text: your first upload (chunk embedding) or first query. Downloads into the Hugging Face cache. | `cd backend && uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"` |
| Ollama answer model `llama3.1:8b` | Explicitly, by you. The app never pulls a model. | `ollama pull llama3.1:8b` |
| Entailment model `cross-encoder/nli-deberta-v3-small` (**optional**) | Never downloaded implicitly. The scorer loads it with `local_files_only=True`; if it is missing it falls back to keyword overlap. Pre-download it only if you want model-backed faithfulness. | `cd backend && uv run python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/nli-deberta-v3-small')"` |

Consequences worth knowing:

- The first upload can take a while (model download + embedding every chunk).
- If the entailment model is not in the local cache, the scorer logs once and judges by
  `local-lexical-overlap`. That is recorded in the eval run's `scorer_id`, so those runs are
  correctly flagged as not comparable with `local-nli:...` runs.
- Changing `KHALEEV_EMBEDDER_ID` changes the embedder and therefore invalidates stored vectors. Use
  a fresh data directory (or re-upload) after changing it, and expect old runs to be flagged.

## Run, test and lint commands

All commands are the repository's real commands; run each from the directory shown.

| Purpose | Command | Working directory |
| --- | --- | --- |
| Install backend deps | `uv sync` | `backend/` |
| Run the API | `uv run uvicorn khaleev.app:app --reload --port 8000` | `backend/` |
| Backend tests | `uv run pytest` (add `-q` for less output) | `backend/` |
| Backend lint | `uv run ruff check .` | `backend/` |
| Install frontend deps | `npm install` | `frontend/` |
| Frontend dev server (port 5173, proxies `/api` → 8000) | `npm run dev` | `frontend/` |
| Frontend type-check + production build | `npm run build` | `frontend/` |
| Frontend tests (single run, non-interactive) | `npm test -- --run` | `frontend/` |
| Frontend tests (watch mode) | `npm test` | `frontend/` |
| Frontend lint | `npm run lint` | `frontend/` |
| Frontend formatting | `npm run format` / `npm run format:check` | `frontend/` |
| Preview a built frontend | `npm run preview` | `frontend/` |

`npm run build` runs both TypeScript projects (`tsc -p tsconfig.json`,
`tsc -p tsconfig.node.json`) and then `vite build`. `npm test` is Vitest, which starts in watch
mode; the `-- --run` form is the CI-equivalent single pass.

## Configuration

Settings come from `KHALEEV_*` environment variables or a `backend/.env` file (copy
`backend/.env.example`). Every setting has a working local default, so `Settings()` constructs with
no environment at all.

One trap in the example file: it sets `KHALEEV_DATA_DIR=./data`, and a **relative** data directory
resolves against the process working directory. Copying `.env.example` unchanged and starting the
server from `backend/` therefore puts data in `backend/data`, not in the default `<repo>/data`.
Remove the line or use an absolute path if you want the default location.

| Variable | Default | Meaning |
| --- | --- | --- |
| `KHALEEV_DATA_DIR` | `<repo>/data` | Root of all local data (SQLite, PDFs, index, golden sets). A relative value resolves against the process working directory. |
| `KHALEEV_EMBEDDER_ID` | `all-MiniLM-L6-v2` | sentence-transformers embedding model. Changing it invalidates existing vectors. |
| `KHALEEV_GENERATOR` | `ollama` | `ollama` (default, local, zero-key) or `cloud`. |
| `KHALEEV_OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server base URL. |
| `KHALEEV_OLLAMA_MODEL` | `llama3.1:8b` | Ollama model name. |
| `KHALEEV_CLOUD_API_KEY` | unset | Optional; only used when `KHALEEV_GENERATOR=cloud`. |
| `KHALEEV_CLOUD_MODEL` | unset | Optional; required with the cloud key. |
| `KHALEEV_CLOUD_BASE_URL` | unset (resolves to `https://api.openai.com/v1`) | Optional OpenAI-compatible endpoint; an explicit value always wins over the provider preset. Must be an absolute `http://`/`https://` URL, and an empty value is rejected. |
| `KHALEEV_CLOUD_PROVIDER` | unset | Optional preset: `openai`, `openrouter`, `groq`, `gemini`, `cerebras` or `github`. Used only when `KHALEEV_CLOUD_BASE_URL` is unset. |
| `KHALEEV_RETRIEVAL_K` | `5` | Top-k chunks per question; recorded with every eval run. |
| `KHALEEV_CHUNK_SIZE` | `600` | Chunk length in characters, validated to 400–800. |
| `KHALEEV_CHUNK_OVERLAP_RATIO` | `0.12` | Overlap between consecutive chunks, validated to 0.10–0.15. |

`GET /api/config` / `PUT /api/config` expose and update `k`, `embedder` and `generator` for the rest
of the process lifetime; they never require a key and never discard an injected dependency.

Cloud generation is opt-in only. It is built solely when `KHALEEV_GENERATOR=cloud` **and** both the
key and the model are set; otherwise the request fails with an actionable 503 and document content
is never sent off-machine.

The cloud endpoint and provider are configured by environment or `backend/.env` only; they are
deliberately not exposed by `GET`/`PUT /api/config`.

## Data directory layout

Everything lives under one directory (`KHALEEV_DATA_DIR`, default `<repo>/data`):

```text
<data_dir>/
├── khaleev.db                    SQLite: documents, chunks, golden_sets,
│                                 eval_runs, eval_run_entries
├── pdfs/
│   └── <content_hash>.pdf        the original upload bytes, named by SHA-256
├── index/
│   └── <document_id>.faiss       one FAISS inner-product index per document
└── golden/
    └── <document_id>.json        hand-editable golden Q&A set per document
```

- `content_hash` is the SHA-256 of the uploaded bytes; it is both the dedupe key and the stored
  filename.
- `khaleev.db` is created and brought to the Alembic head automatically when the API starts; there
  is no manual migration step, and a restart never changes an already-migrated database.
- The FAISS file stores unit-length vectors (`IndexIDMap2` over `IndexFlatIP`), keyed by
  `chunks.id`; a match maps back to a chunk row through `chunks.embedding_ref`, and from there to
  its page number.
- Uploading a document seeds `<data_dir>/golden/<document_id>.json` with `[]` if the file does not
  exist. It never overwrites a file you already filled in.
- Deleting a document removes its rows (cascade), its FAISS file, its stored PDF and its golden
  JSON.

## Walkthrough: your first cited answer

Prerequisite: steps 1–6 of [Zero-key local setup](#zero-key-local-setup) are done, the API is
running on 8000 and `npm run dev` is running on 5173.

1. **Open the Library** at <http://localhost:5173/>.
2. **Upload a real PDF** with the file input. The first upload embeds every chunk, so it may take a
   minute while the embedding model downloads. Success shows the title and page count. Uploading
   the same file again is reported as a dedupe, not a second document.
3. **Select the document** in the list. It becomes the single Q&A target, and the page shows
   `Q&A target: <title>`.
4. **Open Chat** in the navigation. The header names the selected document.
5. **Ask a question**, e.g. `What penalty applies to late filings?`.
6. **Read the answer and its citations.** The answer is prose; below it is one citation chip per
   source page, each labelled with its page number and accompanied by a quote taken from that
   page's retrieved chunk.
7. **Click a citation chip.** The page viewer fetches
   `GET /api/documents/{id}/pages/{n}` and shows that page's extracted text. Pages outside the
   document's range are refused.

If something goes wrong:

| Symptom | Cause and fix |
| --- | --- |
| `no such table` error | Should not happen: the app applies its migrations on startup. If it does, the startup migration failed (for example the data directory is not writable) — check the server log. `cd backend && uv run alembic upgrade head` applies the same history by hand for diagnosis. |
| Ask returns 503 mentioning Ollama | Ollama is not running or the model is not pulled: `ollama serve`, `ollama pull llama3.1:8b`. |
| First upload or ask fails while the embedding model loads | This path has no dedicated error mapping (no 4xx/503 with a repair hint), so check the server log. The download was refused or interrupted: rerun the explicit download command in [First-run model downloads](#first-run-model-downloads) and confirm the model is in the local cache. |
| Ask returns 422 "no indexed text" | The document has no embedded chunks (e.g. ingested before an embedder was available). Delete and re-upload the PDF. |
| Upload returns 400 / 422 | The file is not a PDF (400) or is an unreadable PDF (422). |

The same result over HTTP:

```bash
curl.exe -F "file=@C:\path\to\document.pdf" http://localhost:8000/api/documents
curl.exe -H "Content-Type: application/json" ^
  -d "{\"question\":\"What penalty applies to late filings?\"}" ^
  http://localhost:8000/api/documents/1/ask
```

(The second command is shown for Windows `cmd`; in bash/Git Bash use `\` for line continuation and
single-quote the JSON.)

## Walkthrough: your first eval run

The golden set is the source of truth and it is a file, so an eval needs one edit by hand.

1. **Find the document id.** Either from `GET /api/documents`, or from the database; ids start at 1:

   ```bash
   curl.exe http://localhost:8000/api/documents
   ```

2. **Write at least one golden entry** into `<data_dir>/golden/<document_id>.json`. Uploading
   seeded the file with `[]`; replace the contents with a JSON list. Each entry has exactly the
   three keys `question`, `expected_answer`, `expected_pages`:

   ```json
   [
     {
       "question": "What penalty applies to late filings?",
       "expected_answer": "Late filings incur a flat 200 credit penalty per return.",
       "expected_pages": [4]
     },
     {
       "question": "When is the annual report due?",
       "expected_answer": "The annual report is due within 90 days of the fiscal year end.",
       "expected_pages": [2, 3]
     },
     {
       "question": "Who signs the certification?",
       "expected_answer": "The chief financial officer signs the certification.",
       "expected_pages": [7]
     }
   ]
   ```

   Rules the loader enforces: top level must be a non-empty JSON list; every entry is an object
   with exactly those three keys; `question` and `expected_answer` are non-empty strings;
   `expected_pages` is a non-empty list of integers `>= 1`. An invalid file is rejected with a
   message naming the file and the offending entry index, and `GET /api/documents/{id}/golden`
   returns 422 for it (including for the seeded `[]`).

3. **Open the Eval dashboard** at <http://localhost:5173/evals> with the document selected. It
   shows the golden set read-only, and `k` defaults to 5.
4. **Select "Run evaluation".** The backend retrieves top-5 chunks per golden entry, generates one
   answer per entry, splits each answer into claims, scores every claim, and persists one run plus
   one row per entry — in a single transaction. A failure anywhere rolls the whole run back, so a
   failed run never appears in history.
5. **Read the latest run.** Both metrics are shown to four decimals: `Retrieval hit rate @ k=5` and
   `Answer faithfulness`. Below them is the history list, newest first, with the metrics and
   timestamps of every run.
6. **Try the comparability rule.** Change `k` to 10 and run again: the k=5 run is now flagged as
   not comparable. Or edit the golden JSON and rerun: the file's SHA-256 revision changes, so the
   older run is flagged. Run with the same golden revision, `k`, embedder and scorer, and nothing
   is flagged.

The same run over HTTP (no body means the configured `k`):

```bash
curl.exe -X POST http://localhost:8000/api/documents/1/evals
curl.exe -X POST -H "Content-Type: application/json" -d "{\"k\":10}" http://localhost:8000/api/documents/1/evals
curl.exe http://localhost:8000/api/evals/1
curl.exe http://localhost:8000/api/documents/1/evals
```

An empty golden set is rejected (422) with a "metric undefined" message and writes no run row.

## Metric contracts

These definitions are the contract implemented by the tests and by the persisted `eval_runs` /
`eval_run_entries` rows. Do not change them without deciding that old runs are no longer
comparable.

### Retrieval hit rate @ k

- A golden entry carries a set of expected 1-based pages `E`.
- Retrieve the top-`k` chunks for the entry's question, best first. `k` defaults to 5 and is
  recorded on the run; every entry of a run uses the same `k`.
- The entry **hits** iff at least one retrieved chunk among the first `k` has
  `page_number ∈ E`. Matching is **page-level**: a chunk matches if its page number is in `E`,
  regardless of which part of that page the chunk came from. Duplicate pages neither add score nor
  change the yes/no outcome. A retrieved list shorter than `k` simply has fewer chances.
- `hit_rate@k = (# entries that hit) / (# entries in the golden set)`.
- An empty golden set makes the metric **undefined**: the run is rejected and no run row is
  written.
- Implemented in `backend/src/khaleev/evals/metrics/hit_rate.py` (`entry_hit`, `hit_rate`).

### Answer faithfulness

- Each generated answer is decomposed into **claims**: one claim per sentence that asserts content.
  Page tags (`[page 4]`, `[4]`, `(p. 4)`) are removed before scoring; empty, whitespace-only and
  punctuation-only fragments are dropped. Implemented by `split_claims` in
  `backend/src/khaleev/evals/claims.py`.
- A claim is **supported** iff the entailment scorer judges it entailed by the retrieved chunk(s)
  from the page(s) the answer cited. If the answer cited nothing (or cited only pages that were not
  retrieved), the evidence is **all** top-`k` retrieved chunks. The rule lives in
  `evidence_chunks` / `select_context` in `backend/src/khaleev/evals/scorer.py`.
- Each claim gets one binary supported/unsupported decision.
- `faithfulness = (total supported claims) / (total claims)` summed across all entries of the run —
  counts are summed, not per-entry scores averaged, so an entry with more claims weighs more.
- An answer with **zero claims scores 0.0**; a run whose entries contain no claims scores 0.0.
  There is no division by zero.
- Per-entry `claims`, `supported_claims` and `faithfulness` are persisted, so a run can be audited
  without re-scoring. The scorer's id and version are persisted with the run.

### Rounding: four decimals, half-up

Both aggregate metrics and every per-entry faithfulness value are rounded **half-up to four decimal
places** at persistence and at display. Python's built-in `round` is half-even, so all metric
rounding goes through `Decimal.quantize(..., ROUND_HALF_UP)` in
`backend/src/khaleev/evals/metrics/rounding.py`:

- `7/10 → 0.7000`
- `2/3 → 0.6667` (not banker's rounding)
- `0.03125 → 0.0313` (a tie carries upward, not to even)

The persisted value is the number rounded to four decimal places; the dashboard formats that stored
value to four decimals for display (`0.7` renders as `0.7000`).

### Comparability

Two eval runs are comparable only if they share all four of:

1. the **golden-set revision** — the SHA-256 of the golden JSON file's exact bytes, so any hand edit
   produces a new revision;
2. the same **`k`**;
3. the same **embedding model** (`embedder_id`);
4. the same **scorer** (`scorer_id` — a fallback run is recorded as
   `local-lexical-overlap`, a model-backed one as `local-nli:<model id>`).

The newest run of a document is the reference and is never flagged. Every older run whose signature
differs on any of those four fields is flagged `flagged: true, comparable: false`. The signature is
read **only** from the persisted `eval_runs` row and its `config` JSON — never from live settings —
so changing a setting after a run can never rewrite history. Implemented in
`backend/src/khaleev/evals/comparability.py`.

## The offline test guarantee

Neither test suite performs a network call. This is enforced, not merely intended.

**Backend (`backend/tests/conftest.py`)** installs two **autouse** fixtures for every test:

- `block_network` monkeypatches every outbound socket entry point — `socket.getaddrinfo`,
  `socket.create_connection`, `socket.socket.connect`, `socket.socket.connect_ex` — to raise
  `NetworkAccessBlocked(OSError)` before a packet leaves the process. Any test that accidentally
  reaches for the network fails loudly instead of passing by luck.
- `isolated_data_dir` drops every inherited `KHALEEV_*` variable and pins `KHALEEV_DATA_DIR` to
  pytest's `tmp_path`, so no test can write to your real data directory.

Model-backed paths are exercised through injected fakes and in-process transports:

- `FakeEmbedder` — a deterministic embedder whose vector is seeded from a SHA-256 digest of the
  text, so there is no model and the result is machine-independent.
- `FakeGenerator` — a fixed-answer generator for the ask and eval paths.
- `FakeEntailmentScorer` — constructed verdicts, consumed in order or keyed by claim.
- `httpx.MockTransport` — the real Ollama and cloud clients' request/response code is tested with a
  mocked transport, so no socket is opened.

Production code is written to make that possible: `sentence_transformers` is imported inside the
loader at first use, the embedder/generator/scorer are injected through `create_app(...)`, and the
optional entailment cross-encoder loads with `local_files_only=True` so it can never download
implicitly.

**Frontend** tests run in Vitest + jsdom and mock the API modules (or `fetch`), so nothing leaves the
Node process.

Consequence: `uv run pytest` and `npm test -- --run` pass with networking disabled. The suite proves
the offline promise; the real Ollama path is a manual check, below.

## Manual check against a real Ollama instance

> **Manual check — not automated, and never part of CI.** No test in either suite calls a real
> Ollama server or loads a real model. This section is the only place the real generator is
> exercised, and it is done by a human, by hand. SPEC's testing strategy lists it as level 3 and
> explicitly excludes it from the automated suite.

Do this once per machine (e.g. after installing Ollama or changing the model), with the data
directory you intend to use:

1. `ollama serve` (or confirm the service is running), then `ollama pull llama3.1:8b` and
   `ollama list` to confirm the model is present.
2. Start the API with the SPEC command
   `uv run uvicorn khaleev.app:app --reload --port 8000` from `backend/`, and
   `npm run dev` from `frontend/`.
3. In the UI: upload a real multi-page PDF, select it, and ask a question whose answer is visibly
   on a known page.
4. Confirm all of the following by eye:
   - the answer is about the document, not general knowledge;
   - at least one citation chip is shown, and every chip's page number is a page you can open;
   - clicking a chip shows that page's extracted text;
   - no key-related prompt or error appears anywhere in the UI.
5. Confirm failure reporting is honest: stop Ollama and ask again. The UI must report a 503 with an
   actionable message ("Is Ollama running? ..."), not a blank answer or a traceback.
6. Optionally, run one eval with a real golden entry and check that the persisted `scorer_id` and
   `embedder_id` in `GET /api/evals/{run_id}` name what actually ran.

Record the result of this check; it is not encoded in any test, so nothing will catch a regression
in the real-generator path except this manual pass.

## Runtime dependencies added

SPEC's `## Boundaries → Ask first` requires sign-off for every new runtime dependency. These are the
real lists from `backend/pyproject.toml` and `frontend/package.json`.

### Backend runtime (`[project].dependencies`)

| Package | Why it is here |
| --- | --- |
| `fastapi` | HTTP API and typed request/response models. |
| `python-multipart` | Required by FastAPI to parse the multipart PDF upload. |
| `pydantic-settings` | `Settings`, with `KHALEEV_*` env vars and `.env` support. |
| `sqlalchemy` | ORM and SQLite access for documents, chunks, golden sets and eval history. |
| `alembic` | Schema migrations; the initial migration is the one-way door for the schema. |
| `pypdf` | Per-page text extraction from uploaded PDFs. |
| `sentence-transformers` | Local embeddings (`all-MiniLM-L6-v2`) and, optionally, the local NLI entailment cross-encoder. |
| `faiss-cpu` | Local file-backed vector index (`<data_dir>/index/<document_id>.faiss`). |
| `numpy` | Vector arrays for the FAISS index. |
| `httpx` | Ollama and optional cloud generator HTTP clients; `MockTransport` keeps their tests offline. |
| `uvicorn` | The ASGI server for SPEC's run command (`uv run uvicorn khaleev.app:app --reload --port 8000`); declared here so `uv sync` installs it. |

Backend development-only (`[dependency-groups].dev`): `pytest`, `ruff`.

### Frontend runtime (`dependencies`)

| Package | Why it is here |
| --- | --- |
| `react` | UI library (function components, typed props). |
| `react-dom` | DOM renderer. |
| `react-router-dom` | The three routes: `/` (Library), `/chat` (Chat), `/evals` (Eval dashboard). |

Frontend development-only (`devDependencies`): `vite`, `@vitejs/plugin-react`, `typescript`,
`@types/react`, `@types/react-dom`, `@types/node`, `eslint`, `@eslint/js`, `typescript-eslint`,
`eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`, `globals`, `prettier`, `vitest`,
`jsdom`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`.

## Frontend styling

The UI is styled with **hand-written CSS and no CSS framework**: no Tailwind, no component
library, no CSS-in-JS runtime and no preprocessor, so `frontend/package.json` is untouched by
styling work. The visual system is the R1 layout (`SPEC.md` → `## References → R1`) on the R2
palette — `#F3F4F4` canvas, `#FFFFFF` cards, `#2C2C2C` ink and dark pills, `#612D53` primary accent,
`#853953` secondary accent — locked by SPEC's locked intent 14–16. It supersedes the earlier T21
palette and direction.

| File | Role |
| --- | --- |
| `frontend/src/styles/tokens.css` | Design tokens: the R2 palette, type scale, spacing steps, radius, the single focus ring and the one soft frame shadow. Its header comment records R2's four measured WCAG ratios verbatim, the measured ratio of every further text/background pair the UI introduces, and the floors (body text ≥ 4.5:1, interactive boundaries ≥ 3:1). |
| `frontend/src/styles/base.css` | Reset, global typography, the R1 frame — inset rounded panel and icon rail — and the shared controls (dark pill CTA, buttons, fields, alerts). |
| `frontend/src/styles/components.css` | Every page in R1's anatomy: the Library's hero banner, its "Your documents" section header with the search field, and the three-across document cards; Chat's document context strip, its three ask cards (question form, answer, citations) and the page-viewer card; the eval dashboard's headline metrics, its stacked run cards and the run form and golden set in the side column. |
| `frontend/src/styles/responsive.css` | The 360px, 768px and 1280px layouts: mobile-first defaults plus two widening breakpoints; at 360px the rail is a horizontal strip, everything is one column and the search field takes its own row, at 768px the rail becomes the ~72px column, and at 1280px the two-column grid appears on the pages that still have two columns (the eval dashboard, and Chat with a cited page open). |

All four are imported exactly once, in `frontend/src/main.tsx`; no component imports CSS of its
own, and Vite emits them as a single stylesheet at build time. Highlights:

- One light theme and exactly the R2 palette. `#2C2C2C` ink measures 12.7:1 on the `#F3F4F4` canvas
  and 14.0:1 on a `#FFFFFF` card; white on `#612D53` measures 10.5:1 and on `#853953` 7.8:1
  (WCAG 2.1 AA requires 4.5:1 for body text). Pale tints are accent mixed with white and are
  decorative only.
- A visible `:focus-visible` ring (3px, primary accent, 2px offset) on every link, button, form
  control, citation chip and the page viewer. The single `outline: none` in the stylesheet is the
  Library's search input, whose ring is drawn on the pill wrapper instead, so the field reads as one
  pill rather than two nested ones.
- The active rail item is a filled rounded square with a white glyph, so the active route is a
  shape change as well as a colour change. The shell is the inset panel, the rail and the page
  content — locked intent 17 removed the top bar (pill search, two icon links, avatar) and no later
  task restores it; the search field now lives in the Library's "Your documents" header and appears
  only once at least one document exists.
- Citation chips stay real `<button>`s and read as discrete page references; the eval metric values
  are set in monospace at the top of the type scale, so the latest run's two numbers are the largest
  thing on the dashboard, with each history row's own hit rate right-aligned in the same monospace.
- A flagged (non-comparable) run is marked by a bordered block, the words "Not comparable" and a
  second paragraph naming the persisted field that differs — never by colour alone. The per-entry
  disclosure is a real button carrying `aria-expanded`, and its `aria-controls` target stays in the
  DOM (hidden while collapsed) so the idref always resolves.
- Tap targets are at least 40px tall, focusable controls and long text wrap (`overflow-wrap:
  anywhere`), and no page scrolls horizontally at 360px, 768px or 1280px. Motion is only a colour
  fade and only under `prefers-reduced-motion: no-preference`.

The same frame, rail and card language covers all three pages. T23 built the shell and the Library
page; T24 rebuilt the Chat page (context strip, three ask cards in the left column and the page
viewer as a card in the right column) and the Eval dashboard (headline metrics and stacked run
cards on the left, the run form and golden set on the right) on exactly those tokens — one card
shape, one type scale, one spacing rhythm and one focus ring, with no second palette anywhere.
**T25** then applied locked intent 17: the top bar, the two-across "Selected document" row and the
"Latest eval run" card are gone, the shell is panel + rail + content, the Library is a single
full-width column of hero, Q&A-target banner and document list, its hero is the headline, one
supporting line and the `Upload PDF` control, and the search field sits in the "Your documents"
section header (client-side only, and only once a document exists) — so the landing page issues
exactly one request, `GET /api/documents`. The behaviour locked by SPEC comes first, so every role,
label, string and request on those pages stays exactly as the test suite asserts it.

## Known gaps

No open defects in the v1 scope. The two backend defects a live run of v0.1.0 exposed — the app not
applying migrations on startup, and `uvicorn` being undeclared — are fixed; see
[Zero-key local setup](#zero-key-local-setup) and the dependency table above. The third gap, the
missing frontend stylesheet, is fixed as well: the UI is styled by the hand-written CSS described
in [Frontend styling](#frontend-styling).

Not a defect, but worth knowing: the API serves `/api` only. `backend/src/khaleev/app.py` has no
static-file mount for `frontend/dist/` and no CORS middleware. That matches the SPEC's development
model ("`vite dev` proxies to the API"), which is the supported path; `npm run build` output is
simply not served by uvicorn.

The v1 scope is complete: upload, per-page extraction and chunking, local embeddings and FAISS
retrieval, cited answers, golden sets, both metrics, eval persistence and the dashboard with
comparability flags all work and are covered by the offline test suites.

## API surface

All responses are typed Pydantic models; all routes are mounted under `/api`.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/documents` | Multipart PDF upload. `201` for a new file, `200` with the existing document for identical bytes. |
| `GET` | `/api/documents` | List documents (oldest first). |
| `GET` | `/api/documents/{id}` | Document detail, including its content hash. |
| `GET` | `/api/documents/{id}/pages/{n}` | Extracted text of page `n` (1-based), rebuilt from that page's chunks. |
| `DELETE` | `/api/documents/{id}` | Delete the document, its rows, vectors, stored PDF and golden file. |
| `POST` | `/api/documents/{id}/ask` | `{question}` → `{answer, citations: [{page, quote}]}` with at least one citation. |
| `GET` | `/api/documents/{id}/golden` | The validated golden set (read-only), with its revision. |
| `POST` | `/api/documents/{id}/evals` | Start an eval run; optional `{k}`. Returns the persisted run with both metrics. |
| `GET` | `/api/evals/{run_id}` | One run with its per-entry results. |
| `GET` | `/api/documents/{id}/evals` | Run history, newest first, each row flagged `comparable` / `flagged`. |
| `GET` | `/api/config` | Current `k`, embedder and generator choice. |
| `PUT` | `/api/config` | Partial update of `k`, `embedder` and/or `generator`. |

Domain errors are mapped once, in `backend/src/khaleev/app.py`: `400` not a PDF, `422` corrupt PDF /
invalid or empty golden set / undefined metric / no context, `404` unknown document, page or run,
`503` generator or scorer unavailable. Domain errors answer `{"detail": "<message>"}`; FastAPI's own
request-validation 422 keeps its standard `detail` list shape.
