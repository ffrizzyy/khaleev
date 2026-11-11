"""Retrieval over one document's chunks.

``index`` holds the local FAISS wrapper; ``search`` (T07) composes it with the
chunks table to return page-attributed results. Nothing here imports FastAPI or
holds a session, so retrieval stays a library the API and the evals share.
"""

from __future__ import annotations

from khaleev.retrieval.index import VectorIndex, VectorMatch, embedding_ref, index_path

__all__ = ["VectorIndex", "VectorMatch", "embedding_ref", "index_path"]
