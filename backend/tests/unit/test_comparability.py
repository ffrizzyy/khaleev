"""Unit tests for eval-run comparability (T17, AC10, SPEC "History comparability").

Two runs are comparable only when they share the same persisted configuration:
the golden-set revision, ``k``, the embedder id and the scorer id. The flag is a
pure function of the persisted rows — never of in-process state — so a run made
after changing ``k`` is flagged from what the database recorded, not from what
the current settings happen to say.

These tests use tiny plain stubs instead of SQLAlchemy rows: the module reads
only ``config["golden_set_revision"]`` and four columns, so a dataclass proves
that the comparison depends on nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from khaleev.evals.comparability import (
    SIGNATURE_FIELDS,
    RunSignature,
    compare_runs,
    newest_first,
    run_signature,
)

BASE = datetime(2026, 11, 12, 9, 0, 0)


@dataclass
class StubRun:
    """The persisted fields comparability is allowed to read."""

    id: int
    created_at: datetime
    k: int = 5
    embedder_id: str = "all-MiniLM-L6-v2"
    scorer_id: str = "fake-entailment"
    config: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.config is None:
            self.config = {"golden_set_revision": "rev-a"}


def _run(
    run_id: int,
    *,
    minutes: int,
    k: int = 5,
    revision: str = "rev-a",
    embedder_id: str = "all-MiniLM-L6-v2",
    scorer_id: str = "fake-entailment",
) -> StubRun:
    return StubRun(
        id=run_id,
        created_at=BASE + timedelta(minutes=minutes),
        k=k,
        embedder_id=embedder_id,
        scorer_id=scorer_id,
        config={"golden_set_revision": revision},
    )


def test_signature_reads_the_four_persisted_comparability_fields() -> None:
    run = _run(1, minutes=0, k=7, revision="rev-1", embedder_id="emb-1", scorer_id="sc-1")

    assert run_signature(run) == RunSignature(
        golden_set_revision="rev-1",
        k=7,
        embedder_id="emb-1",
        scorer_id="sc-1",
    )
    assert SIGNATURE_FIELDS == ("golden_set_revision", "k", "embedder_id", "scorer_id")


def test_newest_first_orders_by_timestamp_then_id() -> None:
    older = _run(1, minutes=0)
    newer = _run(2, minutes=5)
    tie = _run(3, minutes=5)

    assert [run.id for run in newest_first([older, newer, tie])] == [3, 2, 1]


def test_no_runs_has_no_comparisons() -> None:
    assert compare_runs([]) == []


def test_a_same_config_pair_is_not_flagged() -> None:
    older = _run(1, minutes=0)
    newer = _run(2, minutes=5)

    comparisons = compare_runs([older, newer])

    assert [c.run_id for c in comparisons] == [2, 1]
    assert [c.flagged for c in comparisons] == [False, False]
    assert all(c.comparable for c in comparisons)


def test_a_different_k_pair_flags_the_run_that_disagrees() -> None:
    k5 = _run(1, minutes=0, k=5)
    k10 = _run(2, minutes=5, k=10)

    comparisons = compare_runs([k5, k10])

    by_id = {c.run_id: c for c in comparisons}
    assert by_id[2].flagged is False  # the reference run is always comparable
    assert by_id[2].comparable is True
    assert by_id[1].flagged is True
    assert by_id[1].comparable is False
    assert by_id[1].signature.k == 5
    assert by_id[2].signature.k == 10


def test_every_differing_field_flags_the_older_run() -> None:
    for field, value in (
        ("revision", "rev-b"),
        ("embedder_id", "other-embedder"),
        ("scorer_id", "other-scorer"),
    ):
        older = _run(1, minutes=0)
        newer = _run(2, minutes=5, **{field: value})

        comparisons = compare_runs([older, newer])

        assert [c.flagged for c in comparisons] == [False, True], field


def test_a_missing_revision_is_an_empty_signature_value_not_a_crash() -> None:
    run = StubRun(id=1, created_at=BASE, config={})

    assert run_signature(run).golden_set_revision == ""
