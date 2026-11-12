"""Eval routes: start a run, read one run, list a document's history (T17).

The routes are thin. They validate transport-level concerns (an integer id, an
optional ``k``), delegate to ``khaleev.services.evals`` and convert persisted
rows into the typed models in ``khaleev.api.schemas``. Everything that decides a
metric lives in the eval layer; everything that decides a status code lives in
``khaleev.app``'s exception handlers.

Three contracts are encoded here:

* **The run records the config it used.** ``POST`` returns the persisted row with
  both metrics, its ``k`` and the full ``config`` JSON — including the
  golden-set revision — so a later comparison reads the database, never memory
  (AC5, AC10).
* **History is newest first and flagged.** ``GET /api/documents/{id}/evals``
  compares each persisted run with the document's most recent run using
  :mod:`khaleev.evals.comparability` and returns an explicit ``flagged`` /
  ``comparable`` pair per row (AC6, AC10).
* **A failed run leaves no history.** The service commits once; on any failure
  it rolls back, and the error is mapped centrally. A scorer that cannot judge
  at all (its contract says fall back, but an injected one may not) is surfaced
  as the same actionable 503 as an unreachable generator rather than a 500.

Both the embedder and generator come from the app's injected services, and the
scorer from a new ``ScorerDep``; tests inject all three fakes, so the suite stays
offline (SPEC AC8, Locked intent #12).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from khaleev.api import schemas
from khaleev.api.deps import (
    EmbedderDep,
    GeneratorDep,
    ScorerDep,
    ServicesDep,
    SessionDep,
)
from khaleev.evals.comparability import compare_runs, newest_first
from khaleev.generation import GenerationError
from khaleev.models import EvalRun as EvalRunRow
from khaleev.services import documents
from khaleev.services.evals import get_eval_run, list_eval_runs, run_eval

router = APIRouter(tags=["evals"])


def _run_fields(run: EvalRunRow) -> dict[str, Any]:
    """The persisted fields every eval response shares."""
    return {
        "id": run.id,
        "document_id": run.document_id,
        "created_at": run.created_at,
        "k": run.k,
        "embedder_id": run.embedder_id,
        "scorer_id": run.scorer_id,
        "hit_rate": run.hit_rate,
        "faithfulness": run.faithfulness,
        "config": dict(run.config or {}),
    }


def _as_run(run: EvalRunRow) -> schemas.EvalRun:
    return schemas.EvalRun(**_run_fields(run))


def _as_detail(run: EvalRunRow) -> schemas.EvalRunDetail:
    entries = [
        schemas.EvalRunEntry(
            golden_index=entry.golden_index,
            hit=entry.hit,
            answer=entry.answer,
            claims=entry.claims,
            supported_claims=entry.supported_claims,
            faithfulness=entry.faithfulness,
        )
        for entry in run.entries
    ]
    return schemas.EvalRunDetail(**_run_fields(run), entries=entries)


def _as_summary(run: EvalRunRow, *, flagged: bool) -> schemas.EvalRunSummary:
    return schemas.EvalRunSummary(
        **_run_fields(run),
        comparable=not flagged,
        flagged=flagged,
    )


def _run_or_unavailable(**kwargs: Any) -> EvalRunRow:
    """Run the eval, translating an unavailable scorer into the 503 domain error.

    The generator already raises :class:`GenerationError` (mapped to 503). The
    default scorer falls back instead of raising, so a ``RuntimeError`` escaping
    ``run_eval`` can only come from an injected scorer that cannot judge at all;
    it deserves the same actionable 503, not a 500 traceback.
    """
    try:
        return run_eval(**kwargs)
    except GenerationError:
        raise
    except RuntimeError as exc:
        raise GenerationError(
            "the faithfulness scorer is unavailable "
            f"({exc}); install the local entailment model or remove the custom "
            "scorer, then retry the eval"
        ) from exc


@router.post(
    "/documents/{document_id}/evals",
    response_model=schemas.EvalRun,
)
def start_eval(
    document_id: int,
    session: SessionDep,
    services: ServicesDep,
    embedder: EmbedderDep,
    generator: GeneratorDep,
    scorer: ScorerDep,
    payload: schemas.StartEvalRequest | None = None,
) -> schemas.EvalRun:
    """Run the document's golden set and return the persisted run.

    ``k`` defaults to the configured retrieval size (5) when the body or the
    field is omitted. An unknown document is 404, a missing golden file is 404,
    an empty or invalid set is 422, and an unavailable generator or scorer is
    503 — all mapped in ``khaleev.app``.
    """
    request = payload if payload is not None else schemas.StartEvalRequest()
    run = _run_or_unavailable(
        session=session,
        document_id=document_id,
        k=request.k,
        embedder=embedder,
        generator=generator,
        scorer=scorer,
        settings=services.settings,
        data_dir=services.settings.data_dir,
    )
    return _as_run(run)


@router.get("/evals/{run_id}", response_model=schemas.EvalRunDetail)
def read_eval_run(run_id: int, session: SessionDep) -> schemas.EvalRunDetail:
    """One run with its per-entry results; 404 when the id is unknown."""
    return _as_detail(get_eval_run(session, run_id))


@router.get(
    "/documents/{document_id}/evals",
    response_model=list[schemas.EvalRunSummary],
)
def read_eval_history(
    document_id: int, session: SessionDep
) -> list[schemas.EvalRunSummary]:
    """The document's runs newest first, each flagged against the latest run.

    The flag is computed by :func:`khaleev.evals.comparability.compare_runs` from
    the persisted ``config`` and columns only, so a settings change after a run
    never rewrites history (AC10). An unknown document is 404; a document with
    no runs is an empty list.
    """
    documents.get_document(session, document_id)
    runs = list_eval_runs(session, document_id)
    comparisons = {comparison.run_id: comparison for comparison in compare_runs(runs)}
    return [
        _as_summary(run, flagged=comparisons[run.id].flagged)
        for run in newest_first(runs)
    ]
