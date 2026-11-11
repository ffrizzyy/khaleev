"""Unit tests for the embedder boundary (T06, Locked intent #10, #12).

The contract under test is deliberately narrow:

* an ``Embedder`` exposes ``embed_texts`` and ``embed_query``, so the ingest and
  retrieval paths can be written against the protocol and never against a model;
* ``FakeEmbedder`` is deterministic — the same text always yields the same
  vector, seeded from the text itself — because the whole test suite depends on
  reproducible vectors and no model is ever loaded (Locked intent #12);
* ``FakeEmbedder`` returns unit vectors, so inner product is cosine similarity;
* ``SentenceTransformerEmbedder`` imports ``sentence_transformers`` only when it
  actually embeds something, so importing the module, constructing the embedder
  and running the suite never download or load a model.

The lazy-import tests poison ``sentence_transformers`` in ``sys.modules`` rather
than relying on the package being absent: that proves the import happens at call
time even on a machine where the dependency is installed.
"""

from __future__ import annotations

import math
import sys
from collections.abc import Sequence

import pytest

from khaleev.config import Settings
from khaleev.ingest import embedding
from khaleev.ingest.embedding import Embedder, FakeEmbedder, SentenceTransformerEmbedder

TEXTS = [
    "Late filings incur a 200 credit penalty.",
    "Refunds are processed within ten business days.",
    "Appeals must be filed within thirty days.",
]


def _norm(vector: Sequence[float]) -> float:
    """The L2 norm of ``vector``."""
    return math.sqrt(sum(value * value for value in vector))


def test_embedder_protocol_declares_the_two_entry_points() -> None:
    assert getattr(Embedder, "_is_protocol", False) is True
    assert hasattr(Embedder, "embed_texts")
    assert hasattr(Embedder, "embed_query")


def test_fake_embedder_satisfies_the_protocol() -> None:
    assert isinstance(FakeEmbedder(), Embedder)


def test_sentence_transformer_embedder_satisfies_the_protocol() -> None:
    assert isinstance(SentenceTransformerEmbedder(), Embedder)


def test_embed_texts_returns_one_vector_per_text() -> None:
    vectors = FakeEmbedder().embed_texts(TEXTS)

    assert len(vectors) == len(TEXTS)
    assert {len(vector) for vector in vectors} == {FakeEmbedder().dimension}


def test_embedding_an_empty_list_returns_no_vectors() -> None:
    assert FakeEmbedder().embed_texts([]) == []


def test_fake_embeddings_are_deterministic_for_the_same_text() -> None:
    embedder = FakeEmbedder()

    first = embedder.embed_texts(TEXTS)
    second = embedder.embed_texts(TEXTS)
    fresh_instance = FakeEmbedder().embed_texts(TEXTS)

    assert first == second == fresh_instance


def test_different_texts_produce_different_vectors() -> None:
    vectors = FakeEmbedder().embed_texts(TEXTS)

    assert len({tuple(vector) for vector in vectors}) == len(TEXTS)


def test_embed_query_matches_embedding_the_same_text_as_a_batch() -> None:
    embedder = FakeEmbedder()

    assert embedder.embed_query(TEXTS[0]) == embedder.embed_texts([TEXTS[0]])[0]


def test_fake_embeddings_are_unit_vectors() -> None:
    vectors = FakeEmbedder().embed_texts(TEXTS)

    for vector in vectors:
        assert _norm(vector) == pytest.approx(1.0, abs=1e-9)


def test_a_repeated_text_embeds_to_the_same_unit_vector_twice() -> None:
    embedder = FakeEmbedder()

    first, second = embedder.embed_texts([TEXTS[0], TEXTS[0]])

    assert first == second
    assert _norm(first) == pytest.approx(1.0)


def test_fake_embedder_dimension_is_configurable() -> None:
    embedder = FakeEmbedder(dimension=8)

    assert len(embedder.embed_query("anything")) == 8


def test_fake_embedder_rejects_a_non_positive_dimension() -> None:
    with pytest.raises(ValueError, match="dimension"):
        FakeEmbedder(dimension=0)


def test_importing_the_module_does_not_import_sentence_transformers() -> None:
    assert "sentence_transformers" not in sys.modules
    assert not hasattr(embedding, "sentence_transformers")


def test_constructing_the_real_embedder_does_not_import_the_model_library(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # ``None`` in ``sys.modules`` makes any import of the package raise, so this
    # passes only if construction never imports it.
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)

    embedder = SentenceTransformerEmbedder()

    assert embedder.model_id == Settings(_env_file=None).embedder_id == "all-MiniLM-L6-v2"


def test_the_real_embedder_accepts_an_explicit_model_id_without_importing() -> None:
    embedder = SentenceTransformerEmbedder("sentence-transformers/paraphrase-MiniLM-L3-v2")

    assert embedder.model_id == "sentence-transformers/paraphrase-MiniLM-L3-v2"


def test_the_model_library_is_imported_only_when_texts_are_embedded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    embedder = SentenceTransformerEmbedder()

    with pytest.raises(ImportError):
        embedder.embed_texts(TEXTS)


class _StubModel:
    """A stand-in for ``SentenceTransformer`` that records how it was called."""

    def __init__(self, vectors: list[list[float]]) -> None:
        self._vectors = vectors
        self.calls: list[tuple[list[str], dict[str, object]]] = []

    def encode(self, texts: list[str], **kwargs: object) -> list[list[float]]:
        self.calls.append((list(texts), kwargs))
        return self._vectors


def test_the_real_embedder_asks_the_model_for_unit_vectors() -> None:
    # The stub replaces the loaded model, so this exercises the adapter without
    # importing sentence-transformers or downloading anything.
    stub = _StubModel([[0.5, 0.5]])
    embedder = SentenceTransformerEmbedder()
    embedder._model = stub

    embedder.embed_texts(["one chunk"])

    _, options = stub.calls[0]
    assert options["normalize_embeddings"] is True
    assert options["convert_to_numpy"] is True


def test_the_real_embedder_loads_its_model_once() -> None:
    stub = _StubModel([[1.0, 0.0]])
    embedder = SentenceTransformerEmbedder()
    embedder._model = stub

    embedder.embed_texts(["first"])
    embedder.embed_query("second")

    assert len(stub.calls) == 2
    assert embedder.model is stub
