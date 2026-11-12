"""Run-over-run comparability from persisted eval-run configuration (T17, AC10).

SPEC's "History comparability" rule is blunt: two eval runs may be charted side
by side only if they share the same golden-set revision, ``k``, embedding model
and scorer. The dashboard must *flag* a run that differs instead of silently
comparing incomparable numbers.

The comparison therefore reads **only the persisted row**: the four columns
``k``, ``embedder_id`` and ``scorer_id`` plus
``config["golden_set_revision"]``. It never reads the live :class:`Settings`,
which may have changed after the run: the config a run was produced under is the
config stored in the database, and that is the whole point of recording it
(SPEC "Eval runs" F5, Boundaries -> Always "record the config").

The reference is the most recent run of the document. The newest run is compared
with itself and is never flagged; every older run whose signature differs on any
of the four fields is. With no runs there is nothing to compare.

The module imports nothing model-backed, so its tests are constructed-input
tests and touch no network (SPEC AC8, Locked intent #12).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, TypeVar

#: The four persisted fields two runs must share to be comparable, in order.
SIGNATURE_FIELDS = ("golden_set_revision", "k", "embedder_id", "scorer_id")


class PersistedRun(Protocol):
    """The persisted shape comparability is allowed to read from a run row."""

    id: int
    created_at: datetime
    k: int
    embedder_id: str
    scorer_id: str
    config: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class RunSignature:
    """The configuration a run's metrics are comparable within."""

    golden_set_revision: str
    k: int
    embedder_id: str
    scorer_id: str


@dataclass(frozen=True, slots=True)
class Comparability:
    """One run's signature and whether it agrees with the latest run."""

    run_id: int
    signature: RunSignature
    flagged: bool

    @property
    def comparable(self) -> bool:
        """The positive spelling of :attr:`flagged`, for the dashboard."""
        return not self.flagged


RunT = TypeVar("RunT", bound=PersistedRun)


def newest_first(runs: Sequence[RunT]) -> list[RunT]:
    """Order runs newest first, breaking equal timestamps by id.

    ``created_at`` can collide when two runs are written in the same clock tick;
    the primary key is monotonic, so ``(created_at, id)`` is a total order and
    the "most recent run" is never ambiguous.
    """
    return sorted(runs, key=lambda run: (run.created_at, run.id), reverse=True)


def run_signature(run: PersistedRun) -> RunSignature:
    """Read the four persisted comparability fields from one run row.

    A missing or non-string revision becomes ``""`` rather than raising: a run
    written by an older code path should still be listable, and an empty value
    simply cannot match a real revision.
    """
    config = run.config if isinstance(run.config, Mapping) else {}
    revision = config.get("golden_set_revision", "")
    if not isinstance(revision, str):
        revision = "" if revision is None else str(revision)
    return RunSignature(
        golden_set_revision=revision,
        k=run.k,
        embedder_id=run.embedder_id,
        scorer_id=run.scorer_id,
    )


def compare_runs(runs: Sequence[PersistedRun]) -> list[Comparability]:
    """Compare every run with the document's most recent run.

    The returned list is newest first, aligned with :func:`newest_first`. The
    most recent run is the reference and is therefore never flagged; an older run
    is flagged exactly when its signature differs from the reference on any of
    the four fields.
    """
    ordered = newest_first(runs)
    if not ordered:
        return []

    reference = run_signature(ordered[0])
    comparisons: list[Comparability] = []
    for run in ordered:
        signature = run_signature(run)
        comparisons.append(
            Comparability(run_id=run.id, signature=signature, flagged=signature != reference)
        )
    return comparisons


__all__ = [
    "SIGNATURE_FIELDS",
    "Comparability",
    "PersistedRun",
    "RunSignature",
    "compare_runs",
    "newest_first",
    "run_signature",
]
