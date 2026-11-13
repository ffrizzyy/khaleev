"""A local, one-file-per-document vector index on top of FAISS inner product.

Design constraints that shape this module:

* **Local-first** (SPEC "Local-only data"): the index is a plain file at
  ``<data_dir>/index/<document_id>.faiss``. There is no server and no shared
  state, and a document's vectors can be removed by deleting one file (AC11).
* **Cosine similarity via inner product**: vectors are unit length (see
  ``khaleev.ingest.embedding``), so FAISS's inner-product index returns cosine
  similarity directly. ``IndexIDMap2`` keeps our own ids — the ``chunks.id``
  values — so a match maps back to a chunk through ``chunks.embedding_ref``.
* **No database and no HTTP**: this module only knows a data directory and a
  document id, so retrieval tests can use it directly and the future search
  layer (T07) can compose it without a session.
* **FAISS stays off the import path**: ``import faiss`` happens inside the
  functions that touch vectors, so importing this module (or calling
  ``index_path``) never loads the native library — the same lazy-import
  discipline as ``khaleev.ingest.embedding``.
* **Durable writes**: ``add`` loads the file, appends and rewrites it, so a
  second process or a fresh instance never silently drops earlier vectors.

The index does not normalise: it stores what it is given and documents that the
caller supplies unit vectors. ``l2_normalize`` in ``khaleev.ingest.embedding``
is the single place that guarantees the invariant.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from khaleev import paths

INDEX_SUFFIX = ".faiss"


def index_path(data_dir: Path, document_id: int) -> Path:
    """``<data_dir>/index/<document_id>.faiss`` without creating anything."""
    return paths.DataPaths.from_data_dir(data_dir).index / f"{document_id}{INDEX_SUFFIX}"


def embedding_ref(vector_id: int) -> str:
    """The ``chunks.embedding_ref`` value that points back at ``vector_id``."""
    return str(vector_id)


@dataclass(frozen=True, slots=True)
class VectorMatch:
    """One search result: the stored vector id and its similarity score."""

    vector_id: int
    score: float


class VectorIndex:
    """The vectors of exactly one document, backed by one FAISS file.

    The file is read on first use (``len``, ``dimension``, ``add``,
    ``search_top_k``) rather than at construction, so building an index object
    for a document that has never been embedded is free and side-effect free.
    """

    def __init__(self, data_dir: Path, document_id: int) -> None:
        self.document_id = document_id
        self._path = index_path(data_dir, document_id)
        self._index: Any | None = None
        self._loaded = False

    @property
    def path(self) -> Path:
        """Where this document's vectors live."""
        return self._path

    def _load(self) -> Any | None:
        """Read the index file once per instance; ``None`` when it is absent."""
        if not self._loaded:
            import faiss

            self._index = faiss.read_index(str(self._path)) if self._path.is_file() else None
            self._loaded = True
        return self._index

    def reload(self) -> None:
        """Forget in-memory state so the next access re-reads the file."""
        self._index = None
        self._loaded = False

    @property
    def dimension(self) -> int | None:
        """The vector width the file was written with, or ``None`` if empty."""
        index = self._load()
        return None if index is None else int(index.d)

    def __len__(self) -> int:
        index = self._load()
        return 0 if index is None else int(index.ntotal)

    def add(self, vectors: Sequence[Sequence[float]], ids: Sequence[int]) -> None:
        """Append ``vectors`` under ``ids`` (the ``chunks.id`` values) and persist.

        Adding nothing is a no-op and never creates a file. A vector of a
        different width than the existing file is rejected, because FAISS cannot
        mix widths and a silent reshape would corrupt similarities.
        """
        if len(vectors) != len(ids):
            raise ValueError(f"got {len(vectors)} vectors but {len(ids)} ids")
        if not vectors:
            return

        import faiss

        matrix = np.ascontiguousarray(np.asarray(vectors, dtype="float32"))
        if matrix.ndim != 2:
            raise ValueError(f"vectors must be a 2-d batch, got shape {matrix.shape}")

        index = self._load()
        if index is None:
            index = faiss.IndexIDMap2(faiss.IndexFlatIP(matrix.shape[1]))
            self._index = index
            self._loaded = True
        elif int(index.d) != matrix.shape[1]:
            raise ValueError(
                f"vector dimension {matrix.shape[1]} does not match "
                f"the index dimension {int(index.d)}"
            )

        index.add_with_ids(
            matrix,
            np.ascontiguousarray(np.asarray(ids, dtype="int64")),
        )
        self._persist()

    def search_top_k(self, query_vector: Sequence[float], k: int) -> list[VectorMatch]:
        """Return at most ``k`` matches, most similar first.

        An absent or empty index returns ``[]`` instead of raising, because "no
        vectors yet" is a normal state for a freshly uploaded document.
        """
        if k < 1:
            raise ValueError(f"k must be >= 1, got {k}")

        index = self._load()
        if index is None or index.ntotal == 0:
            return []

        query = np.ascontiguousarray(np.asarray([list(query_vector)], dtype="float32"))
        if query.shape[1] != int(index.d):
            raise ValueError(
                f"query dimension {query.shape[1]} does not match "
                f"the index dimension {int(index.d)}"
            )

        scores, labels = index.search(query, min(k, int(index.ntotal)))
        return [
            VectorMatch(vector_id=int(label), score=float(score))
            for score, label in zip(scores[0], labels[0], strict=True)
            # FAISS pads with -1 when fewer than k vectors exist; never surface it.
            if int(label) >= 0
        ]

    def delete_document(self) -> None:
        """Remove this document's index file; other documents are untouched."""
        self._path.unlink(missing_ok=True)
        self._index = None
        self._loaded = True

    def _persist(self) -> None:
        """Write the in-memory index to its file atomically."""
        import faiss

        assert self._index is not None  # only reachable after ``add`` created one
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_name(f"{self._path.name}.tmp")
        faiss.write_index(self._index, str(temporary))
        temporary.replace(self._path)


__all__ = ["INDEX_SUFFIX", "VectorIndex", "VectorMatch", "embedding_ref", "index_path"]
