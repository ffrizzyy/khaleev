"""Answer faithfulness (T15, AC7, SPEC "Metric definitions").

SPEC's rule, implemented literally:

* the answer is decomposed into claims by :func:`khaleev.evals.claims.split_claims`
  — one claim per sentence that asserts content;
* a claim is *supported* iff the scorer judges it entailed by the retrieved
  chunk(s) cited in the answer, or, when the answer cites nothing, by all top-k
  retrieved chunks (:func:`khaleev.evals.scorer.select_context`);
* every claim gets one binary decision;
* ``faithfulness = supported claims / claims`` over the whole run, across all
  golden entries, rounded half-up to four decimals (:mod:`rounding`);
* an answer with zero claims scores ``0.0``, not an error and not a division by
  zero (SPEC is explicit about this).

Two layers are exposed. :func:`faithfulness` is the aggregate over counts, which
is what a run persists; :func:`score_answer` is the bridge the eval runner uses
for one entry — split, select context, score, return the counts. Both are pure
Python: scoring only calls the injected :class:`~khaleev.evals.scorer.
EntailmentScorer`, so tests use ``FakeEntailmentScorer`` and load no model
(SPEC AC8, Locked intent #12).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from khaleev.evals.claims import split_claims
from khaleev.evals.metrics.rounding import METRIC_PLACES, round_half_up
from khaleev.evals.scorer import (
    EntailmentScorer,
    PageCitation,
    TextChunk,
    select_context,
)


@dataclass(frozen=True, slots=True)
class FaithfulnessEntry:
    """One answer's claim counts, the unit the aggregate metric sums.

    ``claims`` is the denominator and ``supported`` the numerator; both are
    persisted per entry (SPEC data model) so a run can be re-derived without
    re-scoring.
    """

    claims: int
    supported: int

    def __post_init__(self) -> None:
        if isinstance(self.claims, bool) or not isinstance(self.claims, int):
            raise TypeError(f"claims must be an integer, got {self.claims!r}")
        if isinstance(self.supported, bool) or not isinstance(self.supported, int):
            raise TypeError(f"supported must be an integer, got {self.supported!r}")
        if self.claims < 0:
            raise ValueError(f"claims must be >= 0, got {self.claims}")
        if self.supported < 0:
            raise ValueError(f"supported must be >= 0, got {self.supported}")
        if self.supported > self.claims:
            raise ValueError(
                f"supported claims ({self.supported}) cannot exceed claims ({self.claims})"
            )

    @property
    def faithfulness(self) -> float:
        """This entry's own faithfulness, rounded half-up to four decimals."""
        return entry_faithfulness(self.claims, self.supported)


def entry_faithfulness(claims: int, supported: int) -> float:
    """``supported / claims`` rounded half-up, or ``0.0`` when there are no claims.

    Zero claims is a legitimate answer shape (an empty or whitespace-only answer),
    and SPEC scores it ``0.0`` rather than rejecting the run.
    """
    entry = FaithfulnessEntry(claims=claims, supported=supported)
    if entry.claims == 0:
        return 0.0
    return round_half_up(entry.supported / entry.claims, METRIC_PLACES)


def faithfulness(entries: Sequence[FaithfulnessEntry]) -> float:
    """Return run-level faithfulness: total supported claims / total claims.

    Summing counts (rather than averaging per-entry scores) is what SPEC defines,
    so an entry with many claims weighs more than one with a single claim. A run
    whose entries contain no claims at all scores ``0.0``; an empty list has no
    claims either, and the eval runner rejects an empty golden set before this
    point (``hit_rate`` raises ``MetricUndefinedError`` first).
    """
    total_claims = sum(entry.claims for entry in entries)
    if total_claims == 0:
        return 0.0
    total_supported = sum(entry.supported for entry in entries)
    return round_half_up(total_supported / total_claims, METRIC_PLACES)


def score_claims(
    claims: Sequence[str],
    context: str,
    scorer: EntailmentScorer,
) -> tuple[bool, ...]:
    """Return one binary verdict per claim, in order, from ``scorer``."""
    return tuple(bool(scorer.supports(claim, context)) for claim in claims)


def score_answer(
    answer: str,
    *,
    citations: Sequence[PageCitation],
    retrieved: Sequence[TextChunk],
    scorer: EntailmentScorer,
) -> FaithfulnessEntry:
    """Split ``answer`` into claims and score them against the allowed context.

    The context follows SPEC: the retrieved chunks from the cited pages, or all
    retrieved chunks when the answer cites nothing (see ``select_context``). An
    answer with no claims returns ``FaithfulnessEntry(0, 0)`` without calling the
    scorer at all.
    """
    claims = split_claims(answer)
    context = select_context(citations, retrieved)
    verdicts = score_claims(claims, context, scorer)
    return FaithfulnessEntry(claims=len(claims), supported=sum(verdicts))


__all__ = [
    "FaithfulnessEntry",
    "entry_faithfulness",
    "faithfulness",
    "score_answer",
    "score_claims",
]
