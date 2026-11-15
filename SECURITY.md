# Security policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.x (current: 0.1.0) | Yes |

Only the latest 0.1.x release gets fixes. There is no long-term support branch.

## Reporting a vulnerability

Report privately through GitHub Security Advisories on this repository: open the **Security** tab
and choose **Report a vulnerability** (direct link:
<https://github.com/ffrizzyy/new-project/security/advisories/new>).

Do not open a public issue for a security problem, and do not include document text, API keys or
personal file paths in any report.

This is a single-maintainer project. Reports are handled on a best-effort basis: expect an
acknowledgement when the report is read and a decision on whether it is in scope. There is no bug
bounty and no guaranteed response time.

## What this application is

Khaleev is a local, single-user application, and its threat model follows from that:

- **It binds locally.** The documented run command
  (`uv run uvicorn khaleev.app:app --reload --port 8000`) listens on loopback only — uvicorn's
  default host is `127.0.0.1`, and nothing in `app.py` sets a host or opens a listener of its own,
  so any other interface has to be asked for explicitly with `--host`. The API serves `/api` with no
  static mount and no CORS middleware, and the UI is reached through the Vite dev server on port
  5173, which proxies to port 8000.
- **There is no authentication, by design.** Locked intent 13 in `SPEC.md` puts login, tokens,
  sessions and multi-user state out of scope because the app is single-user and runs on the user's
  own machine. Binding the server to a public interface, running it behind a reverse proxy, or
  port-forwarding it removes the boundary the design relies on; that is a deployment decision, not a
  supported configuration, and reports that depend on it are out of scope.
- **Documents stay on disk.** Everything lives under one local data directory (`KHALEEV_DATA_DIR`,
  default `<repo>/data`): `khaleev.db` (SQLite, which also holds the extracted chunk text),
  `pdfs/<content_hash>.pdf`, `index/<document_id>.faiss` and `golden/<document_id>.json`. File
  permissions are the operating system's; the app does not encrypt the directory. Document text is
  in both the PDFs and the database, so the directory as a whole is the unit to protect. Anyone who
  can read that directory can read the documents.
- **Credentials are environment-only.** `KHALEEV_CLOUD_API_KEY` is read from the environment or
  `backend/.env`, is never logged, echoed in an error or returned by an API response (the base URL is
  not a secret; the key is). `.env` is gitignored and stored in plain text on the machine.

## Network calls

There are three outbound paths, and only one of them can carry document text:

1. **The cloud generator** (`KHALEEV_GENERATOR=cloud` with a key and a model). It is opt-in, and it
   is built only when both the key and the model are set; otherwise the request fails with a 503 and
   nothing leaves the machine. **This is the one place document text can leave the machine.** It
   sends the prompt it builds from the retrieved chunks and the question to the configured
   OpenAI-compatible endpoint; nothing else from the document is sent.
   Free provider tiers commonly reserve training rights on their inputs, which is why this path is
   never the default and why the endpoint and provider are configured by environment or `.env` only.
2. **The local Ollama daemon** at `http://localhost:11434` by default. It is local traffic to a
   process the user runs; the app never pulls a model on its own.
3. **The embedding-model download** on first use (`all-MiniLM-L6-v2` from the Hugging Face model
   hub). It fetches model weights and carries no document text. The optional entailment
   cross-encoder loads with `local_files_only=True`, so it never downloads implicitly.

## In scope

- A crafted PDF that escapes the data directory, overwrites files outside it, or crashes the ingest
  path instead of returning a 4xx.
- Path traversal or injected identifiers in `/api/documents/{id}` routes, page lookups or golden-set
  reads that reach files outside the data directory.
- Retrieval or citation output that cites a page whose chunk was not in the retrieval context, or an
  answer returned without a citation (a correctness and integrity defect, not only a security one).
- A configured cloud key appearing in a log line, an error message, an API response or a test
  fixture.
- A request that goes off-machine while `generator` is not `cloud`.
- A dependency with a known vulnerability that is reachable from the app's own request handling.

## Out of scope

- Missing authentication, or exposing the server to a network, when the deployment itself chose
  that.
- Prompt injection from document content that changes an answer's wording: the model is instructed
  by retrieved text, and answers are generated, not trusted. The consequence that matters — sending
  text to a third party — only happens on the opt-in cloud path and is the user's choice.
- Vulnerabilities in third-party services (Ollama, a cloud provider, the Hugging Face hub) or in
  dependencies that the app does not exercise; report those upstream, and tell us only if the app's
  use of them makes the issue reachable.
- Denial of service from very large uploads on a machine you control.
