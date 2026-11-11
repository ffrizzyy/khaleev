"""Text embedding behind a tiny protocol, with the real model kept off the import path.

Two things in this module matter more than the vectors themselves:

* **The boundary.** Everything upstream (the ingest pipeline, retrieval, the
  evals) talks to ``Embedder`` and never to a model. That is what lets the whole
  test suite run offline with ``FakeEmbedder`` (Locked intent #12, AC8).
* **Laziness.** ``SentenceTransformerEmbedder`` imports ``sentence_transformers``
  inside ``_load_model``, at the first ``embed_texts``/``embed_query`` call, so
  importing this module — or constructing the embedder — never loads a model,
  never imports torch, and never touches the network. The first real call is the
  explicit, documented model download of SPEC assumption A6 and nothing else.

Vectors are unit length. The vector index is a FAISS *inner product* index, so
normalising here (rather than switching the index to L2 distance) is what makes
the returned score an actual cosine similarity in ``[-1, 1]``.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from khaleev.config import Settings

#: Dimensions of ``FakeEmbedder``'s vectors: enough to keep different texts apart.
FAKE_DIMENSION = 32


def l2_normalize(vector: Sequence[float]) -> list[float]:
    """Return ``vector`` scaled to unit length; an all-zero vector stays zero."""
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return [0.0 for _ in vector]
    return [value / norm for value in vector]


@runtime_checkable
class Embedder(Protocol):
    """What the rest of the app needs from an embedding model."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of chunk texts, one unit vector per text, in order."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Embed one query with the same model, so scores are comparable."""
        ...


class FakeEmbedder:
    """A deterministic stand-in: the vector is seeded from the text itself.

    The same text always produces the same unit vector, in any process and on
    any machine (the seed is a SHA-256 digest, not ``hash()``), so ingestion,
    retrieval and eval tests are reproducible without a model. This is the only
    embedder the test suite is allowed to use.
    """

    def __init__(self, dimension: int = FAKE_DIMENSION) -> None:
        if dimension < 1:
            raise ValueError(f"dimension must be positive, got {dimension}")
        self.dimension = dimension

    def _seed(self, text: str) -> int:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big")

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            generator = random.Random(self._seed(text))
            raw = [generator.uniform(-1.0, 1.0) for _ in range(self.dimension)]
            vectors.append(l2_normalize(raw))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]


class SentenceTransformerEmbedder:
    """The real local embedder: sentence-transformers, imported on first use.

    Construction records the model id and nothing else. ``_load_model`` performs
    the module import and the model load together, so no code path can import
    torch or reach the network before something is actually embedded.
    """

    def __init__(self, model_id: str | None = None) -> None:
        self.model_id = model_id if model_id is not None else Settings().embedder_id
        self._model: Any | None = None

    def _load_model(self) -> Any:
        """Import sentence-transformers and load the model — first call only."""
        # Deliberately a function-local import: this is the laziness contract.
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(self.model_id)

    @property
    def model(self) -> Any:
        """The loaded model, fetched on first access and cached afterwards."""
        if self._model is None:
            self._model = self._load_model()
        return self._model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        embeddings = self.model.encode(
            list(texts),
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return [[float(value) for value in row] for row in embeddings]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]


__all__ = [
    "FAKE_DIMENSION",
    "Embedder",
    "FakeEmbedder",
    "SentenceTransformerEmbedder",
    "l2_normalize",
]
