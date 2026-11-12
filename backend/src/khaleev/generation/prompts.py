"""Prompt construction for citation-grounded answers (T08).

``build_prompt`` is a pure function: no settings, no model, no I/O. It receives
the question and the retrieved chunks and returns the exact text a generator is
asked to complete. Two properties are contractual:

* **Every excerpt carries an unambiguous identity.** Each chunk is introduced by
  a header naming a per-prompt excerpt number, the database chunk id and the
  1-based page number, so two chunks from the same page are still distinguishable
  (Locked intent #2, assumption A2).
* **The answer must be page-tagged.** The instruction tells the model to cite
  the page of every claim and to cite nothing that is not in the excerpts;
  ``parse_citations`` then repairs what the model actually produced.

Because the function is pure, its unit tests never load a model and never touch
the network (Locked intent #12).
"""

from __future__ import annotations

from collections.abc import Sequence

from khaleev.retrieval.search import RetrievedChunk

#: The citation contract handed to the model. Kept in one constant so a test can
#: assert it without copying prose.
CITATION_INSTRUCTION = (
    "Cite the source page of every factual claim in square brackets, for "
    "example [page 3] or [pages 3, 5]. Cite only the page numbers listed in "
    "the excerpts above. Never invent a page number. If the excerpts do not "
    "answer the question, say so and cite the pages you consulted."
)


def build_prompt(question: str, retrieved: Sequence[RetrievedChunk]) -> str:
    """Return the generation prompt for ``question`` over ``retrieved``.

    Raises ``ValueError`` for an empty question or an empty retrieval set: a
    citation-grounded prompt cannot be built from nothing, and silently asking
    the model anyway would invite an answer with no valid page to cite.
    """
    cleaned_question = question.strip()
    if not cleaned_question:
        raise ValueError("question must not be empty")
    if not retrieved:
        raise ValueError("cannot build a citation-grounded prompt without retrieved chunks")

    lines: list[str] = [
        "You are Khaleev, a document question-answering assistant.",
        "Answer using ONLY the numbered excerpts below. Do not use outside knowledge.",
        CITATION_INSTRUCTION,
        "",
        "EXCERPTS:",
    ]

    for excerpt_number, chunk in enumerate(retrieved, start=1):
        lines.append(
            f"[excerpt {excerpt_number} | chunk {chunk.chunk_id} | page {chunk.page_number}]"
        )
        lines.append(chunk.text.strip())
        lines.append("")

    lines.extend(
        [
            "QUESTION:",
            cleaned_question,
            "",
            "ANSWER (with page citations):",
        ]
    )
    return "\n".join(lines)


__all__ = ["CITATION_INSTRUCTION", "build_prompt"]
