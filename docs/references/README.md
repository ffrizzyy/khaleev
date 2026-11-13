# References

**No external references were supplied for this project.** `SPEC.md` states this explicitly: the
only source of truth is the verbatim user statement — *"Document Q&A with citations: Upload PDFs,
ask questions, get answers with source page references. Add evaluation (retrieval hit rate, answer
faithfulness) to stand out. called Khaleev"* — refined by one interview round whose answers are
recorded in `SPEC.md` under `## Locked intent`. No reference entries have been invented to fill this
directory.

**This directory is where future references go.** It is empty today apart from this README and the
`.gitkeep` that keeps it in git; nothing here is a citation for the current implementation.

## What is here now

Nothing but this file and the `.gitkeep` that keeps the directory in git. The directory exists, as
the SPEC and the project tree require, so future material has a home.

## What belongs here

Anything external that a later change should be able to cite instead of re-deriving:

- official documentation pages or library guides that justify an implementation choice;
- specification or standards excerpts (for example a metric definition from a paper);
- snapshots of a third-party API's request/response shapes;
- issue threads or release notes that explain a workaround.

Implementation decisions that are internal to this repository are **not** references: they belong in
`docs/architecture.md` (how the code works) or as a new row in `SPEC.md`'s change log (what the
product now requires).

## How to add one

1. Save the material under this directory with a descriptive, lowercase name, e.g.
   `faiss-indexidmap2.md` or `ollama-api-generate-2026-11.json`.
2. Put the source URL, the date you retrieved it, and one sentence on why it matters at the top of
   the file. If you quote a page, keep the quote short and attribute it.
3. If the material changes a requirement, record that in `SPEC.md`'s change log rather than only
   here — a reference informs a decision; it does not silently become the spec.

Keep entries factual and attributable. A reference with no source and no date is not a reference.
