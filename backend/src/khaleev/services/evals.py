"""Application services for eval runs: one honest transaction, durable history (T16).

The eval runner (``khaleev.evals.runner``) turns a golden set into an in-memory
report. This module is where that report becomes history: exactly one
``eval_runs`` row and one ``eval_run_entries`` row per golden entry, committed
together (SPEC F5, AC5; Boundaries -> Always "persist eval runs").

**Error policy: fail fast.** If the golden set is empty, a retrieval is empty, the
generator fails, or a claim cannot be scored, the exception propagates and the
transaction is rolled back — no run row, no entry rows. Continuing past a failed
entry would persist a run whose denominator differs from its peers (some claims
never counted) while its ``k`` and config claim otherwise; that is precisely the
silent incomparability the eval layer exists to prevent. The trade-off is that a
single flaky generation costs the whole run, which is the honest outcome: fix the
generator and rerun.

Runs are append-only. Repeating an eval with the same config writes a second run,
because history — not a single "latest" value — is what makes the dashboard and
the comparability flags meaningful (AC6, AC10). Deleting a document still removes
its history through the schema's ``ON DELETE CASCADE`` (AC11).

The session is injected, so tests run against the migrated temp database and the
API can share the request's session. Nothing here imports a web framework or
builds a real model unless the caller leaves a dependency out: the default
generator comes from :func:`khaleev.generation.build_generator`, the default
scorer is the lazy local one, and the default embedder is resolved by retrieval —
all of which stay offline in tests because tests inject fakes (AC8).
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from khaleev.config import Settings
from khaleev.evals.runner import EvalReport, evaluate
from khaleev.evals.scorer import EntailmentScorer, LocalEntailmentScorer
from khaleev.generation import Generator, build_generator
from khaleev.ingest.embedding import Embedder
from khaleev.models import EvalRun, EvalRunEntry


class EvalRunNotFoundError(LookupError):
    """No eval run with the requested id exists."""


def persist_eval_run(session: Session, report: EvalReport) -> EvalRun:
    """Add the run and its entry rows to the session and flush, without committing.

    The caller owns the transaction. Flushing twice (run, then entries) is what
    gives the entries their ``run_id`` from the database-generated primary key.
    """
    run = EvalRun(
        document_id=report.document_id,
        k=report.k,
        embedder_id=report.embedder_id,
        scorer_id=report.scorer_id,
        hit_rate=report.hit_rate,
        faithfulness=report.faithfulness,
        config=report.config,
    )
    session.add(run)
    session.flush()

    for result in report.entries:
        session.add(
            EvalRunEntry(
                run_id=run.id,
                golden_index=result.golden_index,
                hit=result.hit,
                answer=result.answer,
                claims=result.claims,
                supported_claims=result.supported_claims,
                faithfulness=result.faithfulness,
            )
        )
    session.flush()
    return run


def run_eval(
    session: Session,
    document_id: int,
    *,
    k: int | None = None,
    embedder: Embedder | None = None,
    generator: Generator | None = None,
    scorer: EntailmentScorer | None = None,
    settings: Settings | None = None,
    data_dir: Path | None = None,
) -> EvalRun:
    """Evaluate ``document_id``'s golden set and persist the run atomically.

    ``k`` defaults to ``Settings.retrieval_k`` (5). The generator and scorer
    default to the configured local ones; every dependency can be injected, which
    is how the tests stay offline. On any error the transaction is rolled back and
    the exception is re-raised, so a failed run never appears in history.
    """
    config = settings if settings is not None else Settings()
    active_generator = generator if generator is not None else build_generator(config)
    active_scorer = scorer if scorer is not None else LocalEntailmentScorer()

    try:
        report = evaluate(
            document_id,
            session=session,
            k=k,
            embedder=embedder,
            generator=active_generator,
            scorer=active_scorer,
            settings=config,
            data_dir=data_dir,
        )
        run = persist_eval_run(session, report)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return run


def get_eval_run(session: Session, run_id: int) -> EvalRun:
    """Return the run with its entries available, or raise ``EvalRunNotFoundError``."""
    run = session.get(EvalRun, run_id)
    if run is None:
        raise EvalRunNotFoundError(f"eval run {run_id} does not exist")
    return run


def list_eval_runs(session: Session, document_id: int) -> list[EvalRun]:
    """Every run of one document, oldest first (the dashboard's history order)."""
    return list(
        session.scalars(
            select(EvalRun)
            .where(EvalRun.document_id == document_id)
            .order_by(EvalRun.created_at, EvalRun.id)
        )
    )


__all__ = [
    "EvalRunNotFoundError",
    "get_eval_run",
    "list_eval_runs",
    "persist_eval_run",
    "run_eval",
]
