"""Unit tests for the file-backed FAISS vector index (T06).

What the index has to guarantee for the rest of the app:

* one index file per document, at ``<data_dir>/index/<document_id>.faiss``, so a
  deleted document can be removed without disturbing the others (AC11);
* the ids stored in FAISS are the ids recorded in ``chunks.embedding_ref``, so a
  match can be mapped back to the chunk — and therefore to its page — with one
  lookup (Locked intent #2);
* vectors are unit-length, which makes the inner-product index a cosine index
  and the returned score a similarity in ``[-1, 1]``;
* the index survives a process restart: a fresh ``VectorIndex`` on the same data
  directory returns the same matches;
* the ingest pipeline embeds chunks and writes their vectors, and re-ingesting
  the same bytes never duplicates a vector.

No test builds a ``SentenceTransformerEmbedder``: every vector here comes from
``FakeEmbedder`` or from a hand-written vector, so nothing is downloaded.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from fixtures.pdf_factory import build_pdf
from sqlalchemy import select
from sqlalchemy.orm import Session

from khaleev import paths
from khaleev.ingest.embedding import FakeEmbedder
from khaleev.ingest.pipeline import ingest_pdf
from khaleev.models import Chunk
from khaleev.retrieval.index import VectorIndex, index_path

DOCUMENT_ID = 7


def _unit(*values: float) -> list[float]:
    """Return ``values`` scaled to unit length."""
    norm = math.sqrt(sum(value * value for value in values))
    return [value / norm for value in values]


def _norm(vector: list[float]) -> float:
    """The L2 norm of ``vector``."""
    return math.sqrt(sum(value * value for value in vector))


def _stored_index_files(data_dir: Path) -> list[Path]:
    return sorted(paths.DataPaths.from_data_dir(data_dir).index.glob("*.faiss"))


def _long_page(label: str, lines: int = 3) -> str:
    """A page comfortably longer than the default chunk size, with a marker."""
    body = "\n".join(
        f"{label} line {line}: Late filings incur a flat credit penalty per return number {line}."
        for line in range(lines)
    )
    return f"{label.upper()} PAGE START\n{body}"


def test_the_index_file_is_named_after_the_document(tmp_path: Path) -> None:
    index = VectorIndex(tmp_path, DOCUMENT_ID)

    assert index.path == index_path(tmp_path, DOCUMENT_ID)
    assert index.path == tmp_path.resolve() / "index" / f"{DOCUMENT_ID}.faiss"
    assert not index.path.exists()


def test_a_document_without_an_index_file_has_no_vectors(tmp_path: Path) -> None:
    index = VectorIndex(tmp_path, DOCUMENT_ID)

    assert len(index) == 0
    assert index.search_top_k([1.0, 0.0], 5) == []


def test_add_then_search_returns_matches_in_descending_similarity(tmp_path: Path) -> None:
    index = VectorIndex(tmp_path, DOCUMENT_ID)
    index.add([[1.0, 0.0], [0.0, 1.0], _unit(1.0, 1.0)], [10, 11, 12])

    matches = index.search_top_k([1.0, 0.0], 3)

    assert [match.vector_id for match in matches] == [10, 12, 11]
    assert matches[0].score == pytest.approx(1.0)
    assert matches[1].score == pytest.approx(math.sqrt(0.5))
    assert matches[2].score == pytest.approx(0.0, abs=1e-6)
    assert [match.score for match in matches] == sorted(
        (match.score for match in matches), reverse=True
    )


def test_search_top_k_never_returns_more_than_k(tmp_path: Path) -> None:
    index = VectorIndex(tmp_path, DOCUMENT_ID)
    index.add([[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]], [1, 2, 3])

    assert len(index.search_top_k([1.0, 0.0], 2)) == 2


def test_search_top_k_returns_every_vector_when_k_exceeds_the_count(tmp_path: Path) -> None:
    index = VectorIndex(tmp_path, DOCUMENT_ID)
    index.add([[1.0, 0.0], [0.0, 1.0]], [1, 2])

    matches = index.search_top_k([1.0, 0.0], 99)

    assert sorted(match.vector_id for match in matches) == [1, 2]
    assert all(match.vector_id >= 0 for match in matches)


def test_the_index_reloads_from_disk_in_a_fresh_instance(tmp_path: Path) -> None:
    VectorIndex(tmp_path, DOCUMENT_ID).add([[1.0, 0.0], [0.0, 1.0]], [10, 11])

    reloaded = VectorIndex(tmp_path, DOCUMENT_ID)
    matches = reloaded.search_top_k([0.0, 1.0], 1)

    assert len(reloaded) == 2
    assert matches[0].vector_id == 11
    assert matches[0].score == pytest.approx(1.0)


def test_reload_discards_in_memory_state_and_reads_the_file(tmp_path: Path) -> None:
    index = VectorIndex(tmp_path, DOCUMENT_ID)
    index.add([[1.0, 0.0]], [10])
    # Another writer replaces the file behind this instance's back.
    VectorIndex(tmp_path, DOCUMENT_ID).add([[0.0, 1.0]], [11])

    index.reload()

    assert len(index) == 2
    assert {match.vector_id for match in index.search_top_k([0.0, 1.0], 2)} == {10, 11}


def test_appending_through_a_fresh_instance_keeps_the_earlier_vectors(tmp_path: Path) -> None:
    # ``add`` reads the file first, so appending never drops earlier vectors.
    VectorIndex(tmp_path, DOCUMENT_ID).add([[1.0, 0.0]], [10])

    index = VectorIndex(tmp_path, DOCUMENT_ID)
    index.add([[0.0, 1.0]], [11])

    assert len(index) == 2


def test_vectors_are_unit_length_so_inner_product_is_cosine(tmp_path: Path) -> None:
    vectors = FakeEmbedder().embed_texts(["first chunk", "second chunk", "third chunk"])
    index = VectorIndex(tmp_path, DOCUMENT_ID)
    index.add(vectors, [1, 2, 3])

    self_match = index.search_top_k(vectors[1], 1)[0]

    for vector in vectors:
        assert _norm(vector) == pytest.approx(1.0)
    assert self_match.vector_id == 2
    assert self_match.score == pytest.approx(1.0)


def test_delete_document_removes_the_index_file_and_its_vectors(tmp_path: Path) -> None:
    index = VectorIndex(tmp_path, DOCUMENT_ID)
    index.add([[1.0, 0.0]], [10])

    index.delete_document()

    assert not index.path.exists()
    assert len(index) == 0
    assert index.search_top_k([1.0, 0.0], 5) == []
    assert len(VectorIndex(tmp_path, DOCUMENT_ID)) == 0


def test_delete_document_is_idempotent(tmp_path: Path) -> None:
    index = VectorIndex(tmp_path, DOCUMENT_ID)

    index.delete_document()
    index.delete_document()

    assert not index.path.exists()


def test_deleting_one_document_leaves_the_others_searchable(tmp_path: Path) -> None:
    doomed = VectorIndex(tmp_path, 1)
    survivor = VectorIndex(tmp_path, 2)
    doomed.add([[1.0, 0.0]], [1])
    survivor.add([[0.0, 1.0]], [2])

    doomed.delete_document()

    assert len(_stored_index_files(tmp_path)) == 1
    assert survivor.search_top_k([0.0, 1.0], 1)[0].vector_id == 2


def test_a_dimension_mismatch_is_rejected_on_add(tmp_path: Path) -> None:
    index = VectorIndex(tmp_path, DOCUMENT_ID)
    index.add([[1.0, 0.0]], [10])

    with pytest.raises(ValueError, match="dimension"):
        index.add([[1.0, 0.0, 0.0]], [11])


def test_a_dimension_mismatch_is_rejected_on_search(tmp_path: Path) -> None:
    index = VectorIndex(tmp_path, DOCUMENT_ID)
    index.add([[1.0, 0.0]], [10])

    with pytest.raises(ValueError, match="dimension"):
        index.search_top_k([1.0, 0.0, 0.0], 1)


def test_ids_and_vectors_must_have_the_same_length(tmp_path: Path) -> None:
    index = VectorIndex(tmp_path, DOCUMENT_ID)

    with pytest.raises(ValueError, match="ids"):
        index.add([[1.0, 0.0], [0.0, 1.0]], [10])


def test_adding_nothing_does_not_create_an_index_file(tmp_path: Path) -> None:
    index = VectorIndex(tmp_path, DOCUMENT_ID)

    index.add([], [])

    assert not index.path.exists()
    assert len(index) == 0


@pytest.mark.parametrize("k", [0, -1])
def test_search_rejects_a_non_positive_k(tmp_path: Path, k: int) -> None:
    index = VectorIndex(tmp_path, DOCUMENT_ID)
    index.add([[1.0, 0.0]], [10])

    with pytest.raises(ValueError, match="k"):
        index.search_top_k([1.0, 0.0], k)


def test_ingest_embeds_chunks_and_records_their_index_ids(
    migrated_session: Session, tmp_path: Path
) -> None:
    pdf = build_pdf([_long_page("alpha"), _long_page("beta")])

    result = ingest_pdf(
        migrated_session,
        pdf,
        "guide.pdf",
        tmp_path,
        embedder=FakeEmbedder(),
    )

    chunks = list(
        migrated_session.scalars(
            select(Chunk).order_by(Chunk.page_number, Chunk.chunk_index)
        )
    )
    index = VectorIndex(tmp_path, result.document.id)

    assert chunks
    assert all(chunk.embedding_ref is not None for chunk in chunks)
    assert [int(chunk.embedding_ref) for chunk in chunks] == [chunk.id for chunk in chunks]
    assert len(index) == len(chunks)
    assert index.path == index_path(tmp_path, result.document.id)


def test_an_embedded_chunk_is_found_by_its_own_text(
    migrated_session: Session, tmp_path: Path
) -> None:
    pdf = build_pdf([_long_page("alpha"), _long_page("beta")])
    embedder = FakeEmbedder()
    result = ingest_pdf(migrated_session, pdf, "guide.pdf", tmp_path, embedder=embedder)
    chunks = list(migrated_session.scalars(select(Chunk).order_by(Chunk.id)))

    probe = chunks[-1]
    matches = VectorIndex(tmp_path, result.document.id).search_top_k(
        embedder.embed_query(probe.text), 1
    )

    assert matches[0].vector_id == probe.id
    assert matches[0].score == pytest.approx(1.0)
    assert int(probe.embedding_ref or "-1") == matches[0].vector_id


def test_reingesting_the_same_bytes_does_not_duplicate_vectors(
    migrated_session: Session, tmp_path: Path
) -> None:
    pdf = build_pdf([_long_page("alpha"), _long_page("beta")])
    embedder = FakeEmbedder()
    first = ingest_pdf(migrated_session, pdf, "guide.pdf", tmp_path, embedder=embedder)
    first_vectors = len(VectorIndex(tmp_path, first.document.id))

    second = ingest_pdf(migrated_session, pdf, "guide-copy.pdf", tmp_path, embedder=embedder)

    assert second.created is False
    assert second.document.id == first.document.id
    assert len(VectorIndex(tmp_path, first.document.id)) == first_vectors
    assert len(_stored_index_files(tmp_path)) == 1


def test_two_documents_get_separate_index_files(
    migrated_session: Session, tmp_path: Path
) -> None:
    embedder = FakeEmbedder()
    first = ingest_pdf(
        migrated_session, build_pdf([_long_page("alpha")]), "alpha.pdf", tmp_path, embedder=embedder
    )
    second = ingest_pdf(
        migrated_session, build_pdf([_long_page("beta")]), "beta.pdf", tmp_path, embedder=embedder
    )

    assert first.document.id != second.document.id
    assert index_path(tmp_path, first.document.id).exists()
    assert index_path(tmp_path, second.document.id).exists()
    assert len(_stored_index_files(tmp_path)) == 2
