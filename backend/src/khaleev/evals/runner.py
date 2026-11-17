"""Score a document's golden set into a reproducible eval report (T16, F5, AC5).

One run answers a single question: *how good is this document's Q&A pipeline
right now, under exactly this configuration?* The runner therefore does two
things and nothing else:

* **Scores every golden entry.** For entry ``i`` it retrieves the top-``k``
  chunks for the question, generates one cited answer, splits that answer into
  claims and asks the injected entailment scorer for a binary verdict per claim.
  The result is one :class:`EvalEntryResult` — the in-memory twin of an
  ``eval_run_entries`` row: ``golden_index``, ``hit``, the answer text, the claim
  count, the supported-claim count and the entry's own faithfulness.
* **Aggregates honestly.** ``hit_rate@k`` and ``faithfulness`` come from the
  already-implemented metric functions (T14/T15); this module does not re-derive
  any maths, so the half-up four-decimal rule lives in exactly one place. It also
  captures the configuration the metrics are comparable under: ``k``, the
  embedder id, the generator identity, the scorer id **and version**, the golden
  set revision and the document id (AC10, Boundaries -> Always).

Two contracts matter as much as the numbers:

* **The scorer id is read after scoring.** The default local scorer starts as an
  NLI model and falls back to lexical overlap whenever the model is unavailable.
  Its ``id`` changes when it does, so reading it before the first claim would
  label a fallback run as model-backed and make incomparable scores look
  comparable. :func:`evaluate` reads ``scorer.id`` once every claim has been
  judged.
* **An empty golden set is undefined, not zero.** ``load_golden_set`` rejects an
  empty file as invalid golden data; the runner translates exactly that case into
  the metric's :class:`~khaleev.evals.metrics.hit_rate.MetricUndefinedError` so
  callers have one error to handle for "there is nothing to score".

Nothing is persisted here. :func:`evaluate` is pure orchestration over injected
dependencies and returns a report; ``khaleev.services.evals.run_eval`` owns the
transaction and writes the report, which is what keeps a failed run from leaving
partial history behind. Every model-backed dependency is injected, so the tests
use fakes and no model is loaded or socket opened (SPEC AC8, Locked intent #12).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from khaleev.config import Settings
from khaleev.evals import golden
from khaleev.evals.golden import GoldenSet
from khaleev.evals.metrics.faithfulness import (
    FaithfulnessEntry,
    faithfulness,
    score_answer,
)
from khaleev.evals.metrics.hit_rate import (
    HitRateEntry,
    MetricUndefinedError,
    entry_hit,
    hit_rate,
)
from khaleev.evals.scorer import EntailmentScorer
from khaleev.generation import (
    CloudGenerator,
    Generator,
    OllamaGenerator,
    build_prompt,
    parse_citations,
)
from khaleev.ingest.embedding import Embedder
from khaleev.retrieval.search import resolve_k, retrieve
from khaleev.services.documents import get_document


@dataclass(frozen=True, slots=True)
class EvalEntryResult:
    """One golden entry's scored result, mirrored by one ``eval_run_entries`` row."""

    golden_index: int
    question: str
    expected_pages: tuple[int, ...]
    hit: bool
    answer: str
    claims: int
    supported_claims: int
    faithfulness: float


@dataclass(frozen=True, slots=True)
class EvalReport:
    """Everything one eval run produced, ready to persist as two rows per entry.

    ``config`` is built from the same fields that are persisted in dedicated
    columns, so the columns and the JSON can never disagree about what produced
    the run. The JSON is what a later comparability check reads (AC10).
    """

    document_id: int
    k: int
    embedder_id: str
    scorer_id: str
    scorer_version: str
    golden_set_revision: str
    generator: dict[str, Any]
    hit_rate: float
    faithfulness: float
    entries: tuple[EvalEntryResult, ...]
    served_models: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.k < 1:
            raise ValueError(f"k must be >= 1, got {self.k}")
        for name in ("hit_rate", "faithfulness"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0.0, 1.0], got {value!r}")

    @property
    def config(self) -> dict[str, Any]:
        """The run configuration persisted in ``eval_runs.config`` (AC10).

        ``served_models`` is provenance, not a comparability field: it is merged
        into the ``generator`` object only when this run reported at least one
        model, so a fake/Ollama run's config is byte-identical to before and
        ``"model"`` keeps meaning the configured primary (Locked intent 19).
        """
        generator = dict(self.generator)
        if self.served_models:
            generator["served_models"] = list(self.served_models)
        return {
            "document_id": self.document_id,
            "k": self.k,
            "embedder_id": self.embedder_id,
            "generator": generator,
            "scorer_id": self.scorer_id,
            "scorer_version": self.scorer_version,
            "golden_set_revision": self.golden_set_revision,
        }


def embedder_identity(embedder: Embedder | None, settings: Settings) -> str:
    """The embedding model id to persist.

    An injected fake may expose ``id``; the real embedder exposes ``model_id``.
    With neither (a test double that only embeds), the configured id is the honest
    answer, because that is the model the production path would have used.
    """
    for attribute in ("id", "model_id"):
        value = getattr(embedder, attribute, None)
        if isinstance(value, str) and value:
            return value
    return settings.embedder_id


def generator_identity(generator: Generator, settings: Settings) -> dict[str, Any]:
    """The generator that produced the answers, as JSON-ready config.

    Real generators report their kind and model, so a run made after switching
    from Ollama to the cloud is identifiable from its persisted config alone. A
    test double falls back to its class name; ``kind`` is always a non-empty
    string, which is what a reader (and T17) needs.
    """
    kind = getattr(generator, "kind", None)
    model = getattr(generator, "model", None)

    if not isinstance(kind, str) or not kind:
        if isinstance(generator, OllamaGenerator):
            kind = "ollama"
        elif isinstance(generator, CloudGenerator):
            kind = "cloud"
        else:
            kind = type(generator).__name__

    if model is None:
        if kind == "ollama":
            model = settings.ollama_model
        elif kind == "cloud":
            model = settings.cloud_model

    return {"kind": kind, "model": model}


def _is_empty_golden_file(path: Path) -> bool:
    """True when the golden file is literally the empty list ``[]``.

    Only used after ``load_golden_set`` already rejected the file, to tell "there
    is nothing to score" (a metric-undefined error) apart from "the file is
    broken" (a validation error). Anything unreadable is not this case.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8")) == []
    except (OSError, ValueError):
        return False


def _load_golden_set(data_dir: Path, document_id: int, k: int) -> GoldenSet:
    """Load the golden set, translating the empty-set rejection to the metric error."""
    try:
        return golden.load_golden_set(data_dir, document_id)
    except golden.GoldenSetValidationError as exc:
        if _is_empty_golden_file(golden.golden_path(data_dir, document_id)):
            raise MetricUndefinedError(
                f"hit_rate@{k} is undefined: the golden set for document {document_id} "
                "is empty (0 entries); an eval run against an empty golden set is rejected"
            ) from exc
        raise


def _score_entry(
    *,
    index: int,
    entry: golden.GoldenEntry,
    document_id: int,
    k: int,
    session: Session,
    embedder: Embedder | None,
    generator: Generator,
    scorer: EntailmentScorer,
    settings: Settings,
    data_dir: Path,
    served_models: list[str],
) -> tuple[EvalEntryResult, HitRateEntry, FaithfulnessEntry]:
    """Retrieve, generate, cite and score exactly one golden entry.

    ``served_models`` is the run-local provenance list: the generator's
    per-call ``last_served_model`` is snapshotted immediately after
    ``generate()`` returns, so the report can only ever describe this run's
    calls (Locked intent 19's hazard rule).
    """
    retrieved = retrieve(
        document_id,
        entry.question,
        k,
        session=session,
        embedder=embedder,
        settings=settings,
        data_dir=data_dir,
    )
    if not retrieved.chunks:
        raise ValueError(
            f"golden entry {index}: document {document_id} has no retrievable text; "
            "delete and re-upload the PDF so its chunks are embedded, then rerun the eval"
        )

    answer = generator.generate(build_prompt(entry.question, retrieved.chunks))
    served = getattr(generator, "last_served_model", None)
    if isinstance(served, str) and served:
        served_models.append(served)
    citations = parse_citations(answer, retrieved)
    scored = score_answer(
        answer,
        citations=citations,
        retrieved=retrieved.chunks,
        scorer=scorer,
    )

    # ``retrieved`` is already clamped to k; the slice keeps the page-level rule
    # explicit and identical to what ``hit_rate`` itself does.
    hit = entry_hit(entry.expected_pages, retrieved.chunks[:k])
    result = EvalEntryResult(
        golden_index=index,
        question=entry.question,
        expected_pages=tuple(entry.expected_pages),
        hit=hit,
        answer=answer,
        claims=scored.claims,
        supported_claims=scored.supported,
        faithfulness=scored.faithfulness,
    )
    hit_entry = HitRateEntry(expected_pages=entry.expected_pages, retrieved=retrieved.chunks)
    return result, hit_entry, scored


def evaluate(
    document_id: int,
    *,
    session: Session,
    generator: Generator,
    scorer: EntailmentScorer,
    embedder: Embedder | None = None,
    k: int | None = None,
    settings: Settings | None = None,
    data_dir: Path | None = None,
) -> EvalReport:
    """Score every golden entry of ``document_id`` and return one report.

    Raises :class:`~khaleev.services.documents.DocumentNotFoundError` for an
    unknown document, the golden-set errors from :mod:`khaleev.evals.golden` for a
    missing or invalid file, :class:`MetricUndefinedError` for an empty golden set,
    :class:`~khaleev.generation.GenerationError` when the generator fails, and
    ``ValueError`` when an entry retrieves no text at all. Nothing is written to
    the database: persistence is the caller's transaction.

    ``k`` defaults to ``Settings.retrieval_k`` and is resolved once, so every
    entry is retrieved with the same ``k`` that is recorded on the run. The
    scorer's ``id`` is read after all claims have been judged (see the module
    docstring).
    """
    config = settings if settings is not None else Settings()
    root = Path(data_dir) if data_dir is not None else config.data_dir
    get_document(session, document_id)
    effective_k = resolve_k(k, config)
    golden_set = _load_golden_set(root, document_id, effective_k)

    results: list[EvalEntryResult] = []
    hit_entries: list[HitRateEntry] = []
    faithfulness_entries: list[FaithfulnessEntry] = []
    # Run-local provenance: never module state, never an attribute of the
    # generator, so a previous run's models cannot leak into this report.
    served_models: list[str] = []

    for index, entry in enumerate(golden_set.entries):
        result, hit_entry, scored = _score_entry(
            index=index,
            entry=entry,
            document_id=document_id,
            k=effective_k,
            session=session,
            embedder=embedder,
            generator=generator,
            scorer=scorer,
            settings=config,
            data_dir=root,
            served_models=served_models,
        )
        results.append(result)
        hit_entries.append(hit_entry)
        faithfulness_entries.append(scored)

    # Distinct, first-seen order: a model repeated across entries is one fact.
    distinct_served = tuple(dict.fromkeys(served_models))

    return EvalReport(
        document_id=document_id,
        k=effective_k,
        embedder_id=embedder_identity(embedder, config),
        # Read only now, after every claim has been scored: a fallback run must be
        # recorded under the judge that actually ran, not the one that was intended.
        scorer_id=scorer.id,
        scorer_version=getattr(scorer, "version", ""),
        golden_set_revision=golden_set.revision,
        generator=generator_identity(generator, config),
        hit_rate=hit_rate(hit_entries, effective_k),
        faithfulness=faithfulness(faithfulness_entries),
        entries=tuple(results),
        served_models=distinct_served,
    )


__all__ = [
    "EvalEntryResult",
    "EvalReport",
    "embedder_identity",
    "evaluate",
    "generator_identity",
]
