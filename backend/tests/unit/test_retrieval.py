"""Unit tests for document-scoped top-k retrieval (T07).

Retrieval is the one place where a wrong answer becomes a wrong *citation*, so
the contract under test is narrow and strict:

* ``retrieve`` returns at most ``k`` chunks, most similar first, and each result
  carries the chunk row's ``chunk_id``, ``page_number``, ``chunk_index`` and
  ``text`` plus the similarity ``score`` (Locked intent #2);
* results are document-scoped: two documents whose texts are nearly identical
  never contribute to each other's results, even if a vector index is
  contaminated with the other document's ids (Locked intent #3);
* every result has a real 1-based page number — a zero or missing page is a
  defect, so such chunks are dropped rather than cited (Boundaries -> Always);
* an index id whose chunk row is gone is stale, not fatal: it is skipped and
  logged, and the remaining results still come back;
* ``k`` defaults to ``Settings.retrieval_k`` (5), can be overridden per call,
  and the effective ``k`` is part of the result so an eval run records exactly
  the k it used (metric definitions -> hit rate @ k, AC10).

No test loads a real model: every embedder here is ``FakeEmbedder``.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fixtures.pdf_factory import build_pdf
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from khaleev.config import Settings
from khaleev.ingest.embedding import FakeEmbedder
from khaleev.ingest.pipeline import IngestResult, ingest_pdf
from khaleev.models import Chunk
from khaleev.retrieval.index import VectorIndex
from khaleev.retrieval.search import RetrievalResult, RetrievedChunk, retrieve

SEARCH_LOGGER = "khaleev.retrieval.search"


def _page(label: str, lines: int = 20) -> str:
    """A page comfortably longer than one chunk, distinguishable by ``label``."""
    body = "\n".join(
        f"{label} line {line}: Late filings incur a flat credit penalty per return number {line}."
        for line in range(lines)
    )
    return f"{label.upper()} PAGE START\n{body}"


def _ingest(
    session: Session,
    data_dir: Path,
    pages: list[str],
    filename: str,
    embedder: FakeEmbedder,
) -> IngestResult:
    """Ingest a fixture PDF and embed its chunks with the fake embedder."""
    return ingest_pdf(session, build_pdf(pages), filename, data_dir, embedder=embedder)


def _chunks_of(session: Session, document_id: int) -> list[Chunk]:
    """Every chunk row of one document, in id order."""
    return list(
        session.scalars(select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.id))
    )


def _chunk_count(session: Session, document_id: int) -> int:
    return int(
        session.scalar(
            select(func.count()).select_from(Chunk).where(Chunk.document_id == document_id)
        )
        or 0
    )


def _retrieve(
    session: Session,
    data_dir: Path,
    embedder: FakeEmbedder,
    document_id: int,
    question: str,
    *,
    k: int | None = None,
    settings: Settings | None = None,
    index: VectorIndex | None = None,
) -> RetrievalResult:
    """``retrieve`` wired to the test store, with nothing left implicit."""
    return retrieve(
        document_id,
        question,
        k,
        session=session,
        embedder=embedder,
        index=index,
        settings=settings,
        data_dir=data_dir,
    )


# --- result shape ---------------------------------------------------------


def test_a_result_carries_the_chunk_row_fields(
    migrated_session: Session, tmp_path: Path
) -> None:
    embedder = FakeEmbedder()
    ingested = _ingest(
        migrated_session, tmp_path, [_page("alpha"), _page("beta")], "g.pdf", embedder
    )
    chunk = _chunks_of(migrated_session, ingested.document.id)[0]

    result = _retrieve(
        migrated_session, tmp_path, embedder, ingested.document.id, chunk.text, k=1
    )

    hit = result.chunks[0]
    assert isinstance(hit, RetrievedChunk)
    assert hit.chunk_id == chunk.id
    assert hit.page_number == chunk.page_number
    assert hit.chunk_index == chunk.chunk_index
    assert hit.text == chunk.text
    assert hit.score == pytest.approx(1.0)


def test_results_are_ordered_by_descending_similarity(
    migrated_session: Session, tmp_path: Path
) -> None:
    embedder = FakeEmbedder()
    ingested = _ingest(
        migrated_session, tmp_path, [_page("alpha"), _page("beta")], "g.pdf", embedder
    )

    result = _retrieve(
        migrated_session, tmp_path, embedder, ingested.document.id, "late filing penalty", k=99
    )

    scores = [hit.score for hit in result.chunks]
    assert scores == sorted(scores, reverse=True)
    assert len(result.chunks) == _chunk_count(migrated_session, ingested.document.id)


@pytest.mark.parametrize("k", [1, 2, 5, 99])
def test_retrieval_returns_min_k_n_chunks(
    migrated_session: Session, tmp_path: Path, k: int
) -> None:
    embedder = FakeEmbedder()
    ingested = _ingest(
        migrated_session, tmp_path, [_page("alpha"), _page("beta")], "g.pdf", embedder
    )
    count = _chunk_count(migrated_session, ingested.document.id)
    assert count > 5

    result = _retrieve(
        migrated_session, tmp_path, embedder, ingested.document.id, "credit penalty", k=k
    )

    assert len(result.chunks) == min(k, count)


def test_an_empty_store_returns_an_empty_result(
    migrated_session: Session, tmp_path: Path
) -> None:
    result = _retrieve(migrated_session, tmp_path, FakeEmbedder(), 424_242, "anything", k=5)

    assert result.chunks == ()
    assert len(result) == 0
    assert not result


# --- k resolution ---------------------------------------------------------


def test_k_defaults_to_the_configured_retrieval_k(
    migrated_session: Session, tmp_path: Path
) -> None:
    embedder = FakeEmbedder()
    ingested = _ingest(
        migrated_session, tmp_path, [_page("alpha"), _page("beta")], "g.pdf", embedder
    )
    assert _chunk_count(migrated_session, ingested.document.id) > 5

    result = _retrieve(
        migrated_session, tmp_path, embedder, ingested.document.id, "late filing penalty"
    )

    assert result.k == Settings(_env_file=None).retrieval_k == 5
    assert len(result.chunks) == 5


def test_the_default_k_follows_custom_settings(
    migrated_session: Session, tmp_path: Path
) -> None:
    embedder = FakeEmbedder()
    ingested = _ingest(
        migrated_session, tmp_path, [_page("alpha"), _page("beta")], "g.pdf", embedder
    )
    settings = Settings(_env_file=None, retrieval_k=3)

    result = _retrieve(
        migrated_session,
        tmp_path,
        embedder,
        ingested.document.id,
        "late filing penalty",
        settings=settings,
    )

    assert result.k == 3
    assert len(result.chunks) == 3


def test_an_explicit_k_overrides_the_default(migrated_session: Session, tmp_path: Path) -> None:
    embedder = FakeEmbedder()
    ingested = _ingest(
        migrated_session, tmp_path, [_page("alpha"), _page("beta")], "g.pdf", embedder
    )
    settings = Settings(_env_file=None, retrieval_k=5)

    result = _retrieve(
        migrated_session,
        tmp_path,
        embedder,
        ingested.document.id,
        "late filing penalty",
        k=2,
        settings=settings,
    )

    assert result.k == 2
    assert len(result.chunks) == 2


@pytest.mark.parametrize("k", [0, -1])
def test_a_non_positive_k_is_rejected(
    migrated_session: Session, tmp_path: Path, k: int
) -> None:
    with pytest.raises(ValueError, match="k must be >= 1"):
        _retrieve(migrated_session, tmp_path, FakeEmbedder(), 1, "question", k=k)


# --- document isolation ---------------------------------------------------


def test_near_identical_documents_never_leak_into_each_other(
    migrated_session: Session, tmp_path: Path
) -> None:
    # Same words, different labels: the vectors are close, so only the document
    # scope can keep the two apart.
    embedder = FakeEmbedder()
    alpha = _ingest(migrated_session, tmp_path, [_page("alpha"), _page("alpha")], "a.pdf", embedder)
    beta = _ingest(migrated_session, tmp_path, [_page("beta"), _page("beta")], "b.pdf", embedder)
    alpha_ids = {chunk.id for chunk in _chunks_of(migrated_session, alpha.document.id)}
    beta_ids = {chunk.id for chunk in _chunks_of(migrated_session, beta.document.id)}
    assert not alpha_ids & beta_ids

    # Query alpha with beta's exact text: if scope leaked, beta's chunks would
    # come back at score 1.0.
    probe = _chunks_of(migrated_session, beta.document.id)[0]
    result = _retrieve(
        migrated_session, tmp_path, embedder, alpha.document.id, probe.text, k=99
    )

    returned = {hit.chunk_id for hit in result.chunks}
    assert returned
    assert returned <= alpha_ids
    assert returned.isdisjoint(beta_ids)


def test_an_index_contaminated_with_another_documents_id_is_quarantined(
    migrated_session: Session, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    embedder = FakeEmbedder()
    alpha = _ingest(migrated_session, tmp_path, [_page("alpha"), _page("beta")], "a.pdf", embedder)
    beta = _ingest(migrated_session, tmp_path, [_page("beta"), _page("alpha")], "b.pdf", embedder)
    foreign = _chunks_of(migrated_session, beta.document.id)[0]
    # Simulate a corrupted/merged index: beta's chunk id lands in alpha's file.
    VectorIndex(tmp_path, alpha.document.id).add(
        [embedder.embed_texts([foreign.text])[0]], [foreign.id]
    )

    with caplog.at_level(logging.WARNING, logger=SEARCH_LOGGER):
        result = _retrieve(
            migrated_session, tmp_path, embedder, alpha.document.id, foreign.text, k=99
        )

    returned = [hit.chunk_id for hit in result.chunks]
    assert foreign.id not in returned
    assert all(
        hit.chunk_id
        in {chunk.id for chunk in _chunks_of(migrated_session, alpha.document.id)}
        for hit in result.chunks
    )
    assert "another document" in caplog.text


# --- stale / malformed rows ----------------------------------------------


def test_a_stale_index_id_is_skipped_and_logged(
    migrated_session: Session, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    embedder = FakeEmbedder()
    ingested = _ingest(
        migrated_session, tmp_path, [_page("alpha"), _page("beta")], "g.pdf", embedder
    )
    stale_id = 987_654
    VectorIndex(tmp_path, ingested.document.id).add(
        [embedder.embed_query("vector without a chunk row")], [stale_id]
    )
    live_ids = {chunk.id for chunk in _chunks_of(migrated_session, ingested.document.id)}

    with caplog.at_level(logging.WARNING, logger=SEARCH_LOGGER):
        result = _retrieve(
            migrated_session, tmp_path, embedder, ingested.document.id, "stale vector", k=99
        )

    returned = {hit.chunk_id for hit in result.chunks}
    assert stale_id not in returned
    assert returned == live_ids
    assert "no chunk row" in caplog.text


def test_no_result_ever_has_a_zero_page_number(
    migrated_session: Session, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    embedder = FakeEmbedder()
    ingested = _ingest(migrated_session, tmp_path, [_page("alpha")], "g.pdf", embedder)
    poison_text = "unattributable text with no page at all"
    poison = Chunk(
        document_id=ingested.document.id,
        page_number=0,
        chunk_index=99,
        text=poison_text,
        embedding_ref=None,
    )
    migrated_session.add(poison)
    migrated_session.flush()
    poison.embedding_ref = str(poison.id)
    VectorIndex(tmp_path, ingested.document.id).add(
        [embedder.embed_texts([poison_text])[0]], [poison.id]
    )
    migrated_session.commit()

    with caplog.at_level(logging.WARNING, logger=SEARCH_LOGGER):
        result = _retrieve(
            migrated_session, tmp_path, embedder, ingested.document.id, poison_text, k=99
        )

    assert poison.id not in {hit.chunk_id for hit in result.chunks}
    assert result.chunks
    assert all(hit.page_number >= 1 for hit in result.chunks)
    assert "page" in caplog.text
