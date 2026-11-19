"""Unit tests for the plain-prose half of the generation prompt.

A real answer reached the UI as ``**PT Benteng Nusa Bangsa**``: the model emits
markdown because nothing asked it not to, and the interface renders the
asterisks literally. These tests pin the instruction that asks for plain prose
while leaving the citation contract and every excerpt header byte-identical.

Everything here is constructed input; no model is loaded and no socket is opened.
"""

from __future__ import annotations

from khaleev.generation.prompts import (
    CITATION_INSTRUCTION,
    PLAIN_PROSE_INSTRUCTION,
    build_prompt,
)
from khaleev.retrieval.search import RetrievedChunk

RETRIEVED = (
    RetrievedChunk(
        chunk_id=101,
        page_number=1,
        chunk_index=0,
        text="Scope of the document: this agreement covers filings and late payments.",
        score=0.90,
    ),
    RetrievedChunk(
        chunk_id=102,
        page_number=3,
        chunk_index=0,
        text="Late filings incur a flat credit penalty per return.",
        score=0.80,
    ),
    RetrievedChunk(
        chunk_id=103,
        page_number=5,
        chunk_index=0,
        text="The penalty is capped at 200 credits for small organisations.",
        score=0.70,
    ),
)


def test_prompt_asks_for_plain_prose() -> None:
    prompt = build_prompt("What penalty applies to late filings?", RETRIEVED)
    assert PLAIN_PROSE_INSTRUCTION in prompt


def test_plain_prose_instruction_follows_the_citation_instruction() -> None:
    prompt = build_prompt("What penalty applies?", RETRIEVED)
    assert prompt.index(CITATION_INSTRUCTION) < prompt.index(PLAIN_PROSE_INSTRUCTION)


def test_prompt_keeps_the_citation_instruction_verbatim() -> None:
    prompt = build_prompt("What penalty applies?", RETRIEVED)
    assert CITATION_INSTRUCTION in prompt


def test_prompt_keeps_every_excerpt_header() -> None:
    prompt = build_prompt("What penalty applies?", RETRIEVED)
    for excerpt_number, chunk in enumerate(RETRIEVED, start=1):
        header = f"[excerpt {excerpt_number} | chunk {chunk.chunk_id} | page {chunk.page_number}]"
        assert header in prompt
