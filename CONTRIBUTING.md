# Contributing

Khaleev is a single-user, local-first PDF Q&A application: FastAPI, SQLite, FAISS and
sentence-transformers in `backend/`, React and Vite in `frontend/`. This file covers how to run it,
what has to pass before a change is proposed, and the constraints a change must not break.

## Prerequisites

- **uv** (the backend is a uv project; `uv sync` creates `backend/.venv`).
- **Python 3.11 or newer.** `backend/pyproject.toml` declares `requires-python = ">=3.11"`; uv
  resolves an interpreter that satisfies it, so the interpreter on your PATH is a hint rather than a
  gate.
- **Node 20.19 or newer, or any 22.12 or newer release**, plus npm. That is Vite 8's `engines`
  floor; the CI workflow pins Node 20, which resolves to the latest 20.x.
- **No API keys.** Every core feature works with no key configured.
- **Ollama** only if you want to ask a question or run an eval with the default local generator.
  Uploading, listing, page text, golden-set loading and run history all work without it.

## Setup

From the repository root:

```bash
cd backend
uv sync

cd ../frontend
npm install
```

The database and its schema are created on the first API start; there is no manual migration step.

## The two dev commands

Run both, in separate terminals:

```bash
# terminal 1, from backend/
uv run uvicorn khaleev.app:app --reload --port 8000

# terminal 2, from frontend/
npm run dev
```

The API listens on <http://localhost:8000> and serves `/api` only, with no static mount and no CORS
middleware. Vite listens on <http://localhost:5173> and proxies `/api` to port 8000, so the UI is
opened at 5173. `npm run build` produces `frontend/dist/`, and nothing in this repository serves it.

## Checks

Run each from the directory shown.

| Check | Command | Directory |
| --- | --- | --- |
| Backend lint | `uv run ruff check .` | `backend/` |
| Backend tests | `uv run pytest -q` | `backend/` |
| Frontend lint | `npm run lint` | `frontend/` |
| Frontend type-check and build | `npm run build` | `frontend/` |
| Frontend tests | `npm test -- --run` | `frontend/` |
| Frontend formatting | `npx prettier --check .` (`npm run format` writes) | `frontend/` |
| CSS class scan | `node tasks/class-scan.mjs frontend/src` | repository root |

As of this commit the backend suite is 486 tests and the frontend suite is 147 tests in 17 files.
Those numbers describe the suite today, not a target: the gate is a fully green run, so a change
that adds tests is normal and a change that deletes, skips or weakens one is not. Do not tune a
stale count to match.

Both suites run offline. The backend installs autouse fixtures that block outbound sockets and pin
`KHALEEV_DATA_DIR` to a temporary directory; the frontend tests mock the API modules or `fetch`.
Nothing in either suite downloads a model or calls Ollama, so a test that needs the network is a bug
in the test.

`tasks/class-scan.mjs` is a dependency-free Node script that reports CSS classes defined in
`frontend/src` but never used, and classes used but never defined. It must print `(none)` for both
lists and exit 0; it exits non-zero otherwise.

The CI workflow (`.github/workflows/ci.yml`) runs the backend lint and tests and the frontend lint,
build, tests, formatting check and class scan as two independent jobs. CI is the backstop, not an
excuse to skip them: run every gate above before you push, so a formatting or class-scan failure
does not cost you a round trip.

## The pipeline

`SPEC.md` is the source of truth: locked intent, features, metric definitions, boundaries and
acceptance criteria. `tasks/plan.md` turns it into ordered, verifiable tasks, each with its own
acceptance criteria and verify commands, tracked as `- [ ]` and `- [x]` checkboxes in dependency
order. A task moves through spec, plan, build, verify, review and ship; it lands as one commit and
one push, and the checkbox is ticked only once its verify commands pass in full. A task that cannot
meet its acceptance criteria is reported as blocked rather than quietly re-scoped.

## Pre-existing tests are a contract

Do not edit an existing test file to make a change pass. The suite is the evidence for behaviour the
SPEC locks, and a test edited in the same commit as the code it covers proves nothing. If an
assertion genuinely cannot survive a change, name the file and the reason in the pull request and
treat it as a decision to review rather than a detail. New behaviour gets new tests, in a new file
where that is cleaner than extending an old one.

## Local-first is a product constraint

- No telemetry, no hosted service, no accounts, and no required API key.
- Documents, vectors, golden sets and run history stay in the local data directory (`<repo>/data` by
  default: `khaleev.db`, `pdfs/`, `index/`, `golden/`).
- Document text leaves the machine in exactly one case: the user explicitly selects the cloud
  generator (`KHALEEV_GENERATOR=cloud` with a key and a model). The cloud path is opt-in and must
  never become the default; free provider tiers commonly reserve training rights on their inputs.
- A change that adds a runtime dependency, an outbound request or a new required setting is a
  product decision, not an implementation detail. Raise it before writing it.

## Formatting and commits

Frontend code is formatted with Prettier (`frontend/.prettierrc.json`) and the UI is hand-written
CSS with no framework, so component styles live in `frontend/src/styles/`. Commit messages state
what changed and why, in the imperative mood. Do not commit `.env` files, the local `data/`
directory or build output; they are gitignored.

## Reporting

Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md), never in a public
issue. Participation is covered by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
