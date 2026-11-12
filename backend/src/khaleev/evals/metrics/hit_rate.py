"""Retrieval hit rate @ k (T14, AC7, SPEC "Metric definitions").

The definition is deliberately page-level and blunt:

* one golden entry has a set of expected 1-based pages ``E``;
* retrieval returns the top-``k`` chunks for that entry's question, best first;
* the entry **hits** iff at least one of those chunks has ``page_number`` in
  ``E`` - it does not matter which slice of the page the chunk came from, only
  which page it belongs to;
* ``hit_rate@k = hits / #entries`` over the whole golden set.

Two consequences are encoded here rather than left to the caller. The retrieved
list is clamped to its first ``k`` chunks, so a page that only appears at rank
``k + 1`` is a miss (the SPEC bounds the metric by ``k``, not by how much a
retrieval happened to return). And an empty golden set raises
:class:`MetricUndefinedError` instead of returning ``0.0``: dividing by zero
entries has no meaning, and SPEC says a run against an empty set is rejected.

The result is rounded half-up to four decimals (:mod:`rounding`), so the value
persisted in ``eval_runs.hit_rate`` is the value tested here.

This module imports only the standard library and reads nothing but a
``page_number`` attribute from a retrieved chunk. It never loads a model, opens a
database or touches a socket, so its tests are pure constructed-input tests
(SPEC AC8, Locked intent #12), and it stays compatible with
``khaleev.retrieval.search.RetrievedChunk`` without importing it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import islice
from typing import Protocol

from khaleev.evals.metrics.rounding import METRIC_PLACES, round_half_up

#: Default ``k`` for every eval run (SPEC suggestion; also ``Settings.retrieval_k``).
DEFAULT_K = 5


class MetricUndefinedError(ValueError):
    """A metric has no value for the given inputs, so the run must be rejected."""


class PageTagged(Protocol):
    """The one thing the hit rule needs: a chunk that knows its 1-based page."""

    page_number: int


@dataclass(frozen=True, slots=True)
class HitRateEntry:
    """One golden entry's expected pages and the chunks retrieved for its question.

    ``retrieved`` is the retrieval result in rank order (best similarity first);
    :func:`hit_rate` only looks at its first ``k`` chunks.
    """

    expected_pages: Sequence[int]
    retrieved: Sequence[PageTagged]


def entry_hit(expected_pages: Iterable[int], retrieved: Iterable[PageTagged]) -> bool:
    """True iff any retrieved chunk's page is one of ``expected_pages``.

    Matching is by page number alone (SPEC: "regardless of which part of the page
    the chunk came from"). An empty retrieved list is a miss, and duplicated
    pages on either side neither change the outcome nor add score - this is a
    yes/no question per entry, not a count. An empty expected set is invalid
    golden data and raises rather than silently scoring a guaranteed miss.
    """
    expected = set(expected_pages)
    if not expected:
        raise ValueError("expected_pages must not be empty for a golden entry")
    return any(chunk.page_number in expected for chunk in retrieved)


def hit_rate(entries: Sequence[HitRateEntry], k: int = DEFAULT_K) -> float:
    """Return ``hit_rate@k`` for ``entries``, rounded half-up to four decimals.

    ``entries`` is the full golden set; each one is scored by :func:`entry_hit`
    against the first ``k`` of its retrieved chunks. ``k`` is validated because it
    is persisted with the run and must stay comparable (SPEC "History
    comparability"), and an empty golden set raises :class:`MetricUndefinedError`
    so the caller rejects the run instead of persisting a meaningless ``0.0``.

    A document with fewer chunks than ``k`` is not special-cased: it simply has
    fewer chances to hit and stays in the denominator.
    """
    if isinstance(k, bool) or not isinstance(k, int):
        raise TypeError(f"k must be an integer, got {k!r}")
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}")
    if not entries:
        raise MetricUndefinedError(
            f"hit_rate@{k} is undefined: the golden set is empty (0 entries); "
            "an eval run against an empty golden set is rejected"
        )

    hits = sum(
        1
        for entry in entries
        if entry_hit(entry.expected_pages, islice(entry.retrieved, k))
    )
    return round_half_up(hits / len(entries), METRIC_PLACES)


__all__ = [
    "DEFAULT_K",
    "HitRateEntry",
    "MetricUndefinedError",
    "PageTagged",
    "entry_hit",
    "hit_rate",
]
