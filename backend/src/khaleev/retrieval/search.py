"""Document-scoped top-k retrieval: the bridge between vectors and citations.

The index (``khaleev.retrieval.index``) knows only ids and scores; the database
knows pages and text. This module joins them, and the join is where three SPEC
constraints are enforced:

* **Document scope** (Locked intent #3). Only chunks whose ``document_id`` is the
  requested document may be returned — the per-document index already makes a
  leak unlikely, but a merged or corrupted index file is cross-checked against
  the ``chunks`` rows instead of trusted.
* **Page attribution** (Locked intent #2, Boundaries -> Always). A chunk without
  a usable 1-based page number is dropped rather than surfaced, because an
  unciteable hit is worthless to the ask path and would corrupt hit-rate@k.
* **Stale index tolerance**. A vector id whose chunk row is gone (an index
  written before a re-ingest, or a half-completed delete) is logged and skipped,
  never raised: retrieval must degrade to fewer results, not to an error page.

``k`` resolution lives here too. ``retrieve`` records the effective ``k`` on its
result, so the ask path and the eval runner both persist exactly the k that
produced the retrieved pages — the precondition for comparable hit-rate@k
(SPEC "History comparability", AC10).

Nothing here loads a model or opens a socket on import: the embedder and index
are injected by callers (tests use ``FakeEmbedder``), and the real embedder is
constructed lazily, only when a call actually needs it (Locked intent #12).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from khaleev import db
from khaleev.config import Settings
from khaleev.ingest.embedding import Embedder, SentenceTransformerEmbedder
from khaleev.models import Chunk
from khaleev.retrieval.index import VectorIndex, VectorMatch

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """One retrieved chunk with everything a citation and an eval need."""

    chunk_id: int
    page_number: int
    chunk_index: int
    text: str
    score: float


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    """The hits for one question, plus the ``k`` that produced them.

    ``k`` is the effective ``k`` of the call (the default resolved from settings
    or the caller's override), *not* ``len(chunks)``: a document with three
    chunks asked for ``k=5`` reports ``k == 5`` and three chunks. Eval runs
    persist this value so hit-rate@k stays comparable across runs.
    """

    document_id: int
    k: int
    chunks: tuple[RetrievedChunk, ...]

    def __len__(self) -> int:
        return len(self.chunks)

    def __iter__(self) -> Iterator[RetrievedChunk]:
        return iter(self.chunks)


def resolve_k(k: int | None, settings: Settings | None = None) -> int:
    """Return the effective ``k``: the caller's value or the configured default.

    A non-positive ``k`` is a programming error, not a "return nothing", so it
    raises before any embedding or database work happens.
    """
    config = settings if settings is not None else Settings()
    resolved = config.retrieval_k if k is None else k
    if resolved < 1:
        raise ValueError(f"k must be >= 1, got {resolved}")
    return resolved


def _resolve_settings(settings: Settings | None) -> Settings:
    return settings if settings is not None else Settings()


@contextmanager
def _open_session(data_dir: Path) -> Iterator[Session]:
    """A short-lived session for callers that did not bring one."""
    engine = db.create_engine(data_dir)
    try:
        with db.create_session_factory(engine)() as session:
            yield session
    finally:
        engine.dispose()


def _to_hits(
    session: Session,
    document_id: int,
    matches: Sequence[VectorMatch],
) -> tuple[RetrievedChunk, ...]:
    """Map index matches back to their chunk rows, in the index's score order.

    Rows are fetched in one query and then checked one by one, so the reason a
    match is dropped is visible in the log: a missing row is stale, a foreign
    row is a scope violation, and a bad page is an attribution defect.
    """
    vector_ids = [match.vector_id for match in matches]
    rows = session.scalars(select(Chunk).where(Chunk.id.in_(vector_ids))).all()
    by_id = {int(chunk.id): chunk for chunk in rows}

    hits: list[RetrievedChunk] = []
    for match in matches:
        chunk = by_id.get(match.vector_id)
        if chunk is None:
            logger.warning(
                "skipping stale index id %s for document %s: no chunk row",
                match.vector_id,
                document_id,
            )
            continue
        if int(chunk.document_id) != document_id:
            logger.warning(
                "skipping index id %s: chunk belongs to another document (%s, not %s)",
                match.vector_id,
                chunk.document_id,
                document_id,
            )
            continue
        if chunk.page_number is None or int(chunk.page_number) < 1:
            logger.warning(
                "skipping chunk %s of document %s: no usable 1-based page number",
                chunk.id,
                document_id,
            )
            continue
        hits.append(
            RetrievedChunk(
                chunk_id=int(chunk.id),
                page_number=int(chunk.page_number),
                chunk_index=int(chunk.chunk_index),
                text=chunk.text,
                score=float(match.score),
            )
        )
    return tuple(hits)


def retrieve(
    document_id: int,
    question: str,
    k: int | None = None,
    *,
    session: Session | None = None,
    embedder: Embedder | None = None,
    index: VectorIndex | None = None,
    settings: Settings | None = None,
    data_dir: Path | None = None,
) -> RetrievalResult:
    """Return the ``min(k, n)`` best chunks of ``document_id`` for ``question``.

    Results are ordered by descending similarity (cosine, because the vectors are
    unit length) and carry the chunk row's page, index and text. ``k`` defaults
    to ``Settings.retrieval_k`` (5) and must be >= 1.

    Every dependency is injectable: ``session`` (one is opened and closed
    otherwise), ``embedder`` (``SentenceTransformerEmbedder`` otherwise, loaded
    only when this call embeds), ``index`` (``VectorIndex(data_dir, document_id)``
    otherwise) and ``settings``/``data_dir`` for the defaults. The ask path and
    the eval runner call this function unchanged; tests inject ``FakeEmbedder``.
    """
    config = _resolve_settings(settings)
    effective_k = resolve_k(k, config)
    root = Path(data_dir) if data_dir is not None else config.data_dir
    active_index = index if index is not None else VectorIndex(root, document_id)
    active_embedder = (
        embedder if embedder is not None else SentenceTransformerEmbedder(config.embedder_id)
    )

    query_vector = active_embedder.embed_query(question)
    matches = active_index.search_top_k(query_vector, effective_k)
    if not matches:
        return RetrievalResult(document_id=document_id, k=effective_k, chunks=())

    if session is not None:
        chunks = _to_hits(session, document_id, matches)
    else:
        with _open_session(root) as owned_session:
            chunks = _to_hits(owned_session, document_id, matches)

    return RetrievalResult(document_id=document_id, k=effective_k, chunks=chunks)


__all__ = ["RetrievalResult", "RetrievedChunk", "resolve_k", "retrieve"]
