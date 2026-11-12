"""The entailment boundary for answer faithfulness (T15, AC7, assumption A3).

One tiny protocol decides every claim: ``supports(claim, context) -> bool``. The
metric, the eval runner and the tests all talk to that protocol, never to a model
class, which is what keeps the whole test suite offline (SPEC AC8, Locked intent
#12).

Three implementations ship here:

* :class:`LocalEntailmentScorer` — the default. A small sentence-transformers
  cross-encoder NLI model (SPEC suggestion:
  ``cross-encoder/nli-deberta-v3-small``) imported **inside the loader**, at the
  first scoring call, and loaded with ``local_files_only=True`` so it can never
  trigger an implicit download. If the package is missing, the model is not in
  the local cache, or a prediction fails, it logs once and judges by
  :class:`LexicalOverlapScorer` instead of crashing the run. Its ``id`` reports
  whichever judge actually ran, so a fallback run is not falsely comparable with
  a model-backed one (SPEC "History comparability").
* :class:`LexicalOverlapScorer` — a deterministic keyword-overlap judge. It
  requires most content words of the claim (and every number) to occur in the
  context. This is the fallback, and it is fully unit-tested with plain strings.
* :class:`FakeEntailmentScorer` — constructed verdicts consumed in call order or
  keyed by claim. Every metric test uses it; it loads nothing.

Scorer identity is exposed as ``id`` and ``version``. T16 persists both with the
run; scores are only comparable within the same scorer.

``select_context`` implements SPEC's evidence rule: when the answer cites pages,
only the retrieved chunks from those pages support its claims; when it cites
nothing (or cites a page that was not retrieved), all top-k retrieved chunks do.

No module-level import of ``sentence_transformers``, torch, FAISS or SQLAlchemy
lives here: importing this module is free.
"""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

#: Version of this scorer implementation, persisted with every run.
SCORER_VERSION = "1"

#: Component id of the local NLI scorer; the model id is appended to it.
NLI_SCORER_ID = "local-nli"

#: Component id of the deterministic keyword-overlap judge and fallback.
LEXICAL_SCORER_ID = "local-lexical-overlap"

#: The small local NLI model suggested by SPEC and assumption A3.
DEFAULT_NLI_MODEL = "cross-encoder/nli-deberta-v3-small"


@runtime_checkable
class EntailmentScorer(Protocol):
    """What the faithfulness metric needs from an entailment judge.

    ``id`` and ``version`` identify the judge that produced the verdicts; both are
    persisted with an eval run so scores stay comparable only within one scorer.
    """

    id: str
    version: str

    def supports(self, claim: str, context: str) -> bool:
        """True iff ``context`` entails ``claim``."""
        ...


class PageCitation(Protocol):
    """The one thing context selection reads from a citation."""

    page: int


class TextChunk(Protocol):
    """The one thing context selection reads from a retrieved chunk."""

    page_number: int
    text: str


def evidence_chunks(
    citations: Sequence[PageCitation],
    retrieved: Sequence[TextChunk],
) -> tuple[TextChunk, ...]:
    """The retrieved chunks that may support the answer's claims.

    Cited pages win: only chunks whose ``page_number`` was cited are evidence.
    When the answer cites nothing — or only pages that were not retrieved, which
    is a citation defect rather than evidence — every retrieved chunk is used.
    ``retrieved`` is expected in rank order, and the order is preserved.
    """
    chunks = tuple(retrieved)
    if not chunks:
        return ()

    cited_pages = {citation.page for citation in citations}
    if cited_pages:
        cited = tuple(chunk for chunk in chunks if chunk.page_number in cited_pages)
        if cited:
            return cited

    return chunks


def select_context(
    citations: Sequence[PageCitation],
    retrieved: Sequence[TextChunk],
) -> str:
    """Join the evidence chunks into one context string for the scorer.

    Chunks are separated by a blank line so an NLI model sees them as distinct
    passages; each chunk's own whitespace is trimmed. No chunks means ``""``.
    """
    return "\n\n".join(
        text for chunk in evidence_chunks(citations, retrieved) if (text := chunk.text.strip())
    )


#: Stems too common to signal that a claim is grounded in the context.
_STOPWORDS = frozenset(
    """
    a about above after again against all am an and any are as at be because been
    before being below between both but by can could did do does doing down during
    each few for from further had has have having he her here hers herself him
    himself his how i if in into is it its itself just me more most my myself no
    nor not now of off on once only or other our ours ourselves out over own same
    she should so some such than that the their theirs them themselves then there
    these they this those through to too under until up very was we were what when
    where which while who whom why will with would you your yours yourself
    yourselves
    """.split()
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _content_tokens(text: str) -> tuple[str, ...]:
    """Lower-cased alphanumeric tokens with common stopwords removed."""
    return tuple(
        token
        for token in _TOKEN_RE.findall(text.lower())
        if token not in _STOPWORDS
    )


class LexicalOverlapScorer:
    """A deterministic keyword-overlap judge, used when no NLI model is available.

    A claim is supported when every number it mentions occurs in the context and
    at least ``threshold`` of its distinct content words occur there too. Numbers
    are required because a changed figure is exactly the hallucination this
    metric exists to catch. No model, no randomness, no I/O.
    """

    id = LEXICAL_SCORER_ID
    version = SCORER_VERSION

    def __init__(self, threshold: float = 0.6) -> None:
        if not 0.0 < threshold <= 1.0:
            raise ValueError(f"threshold must be in (0, 1], got {threshold}")
        self.threshold = threshold

    def supports(self, claim: str, context: str) -> bool:
        claim_tokens = set(_content_tokens(claim))
        if not claim_tokens:
            return False

        context_tokens = set(_content_tokens(context))
        if not context_tokens:
            return False

        if any(token.isdigit() and token not in context_tokens for token in claim_tokens):
            return False

        covered = sum(1 for token in claim_tokens if token in context_tokens)
        return covered / len(claim_tokens) >= self.threshold

    def supported(self, claim: str, context: str) -> bool:
        """Alias for :meth:`supports` (the name used by the task plan)."""
        return self.supports(claim, context)


class FakeEntailmentScorer:
    """A deterministic scorer built from constructed verdicts.

    ``verdicts`` is either a mapping of claim text to verdict (unmatched claims
    use ``default``) or a sequence consumed in call order, where the last verdict
    repeats. Every ``(claim, context)`` pair is recorded in ``calls`` so tests can
    assert which context the metric selected. No model is loaded.
    """

    id = "fake-entailment"
    version = "test"

    def __init__(
        self,
        verdicts: Mapping[str, bool] | Sequence[bool] | None = None,
        *,
        default: bool = False,
    ) -> None:
        self._by_claim: dict[str, bool] = {}
        self._sequence: list[bool] = []
        if isinstance(verdicts, Mapping):
            self._by_claim = {str(claim): bool(verdict) for claim, verdict in verdicts.items()}
        elif verdicts is not None:
            self._sequence = [bool(verdict) for verdict in verdicts]

        self.default = bool(default)
        self._position = 0
        self.calls: list[tuple[str, str]] = []

    def supports(self, claim: str, context: str) -> bool:
        self.calls.append((claim, context))
        if claim in self._by_claim:
            return self._by_claim[claim]
        if self._sequence:
            index = min(self._position, len(self._sequence) - 1)
            self._position += 1
            return self._sequence[index]
        return self.default

    def supported(self, claim: str, context: str) -> bool:
        """Alias for :meth:`supports` (the name used by the task plan)."""
        return self.supports(claim, context)


def _softmax(values: Sequence[float]) -> list[float]:
    """Softmax over the model's per-label scores."""
    peak = max(values)
    exps = [math.exp(value - peak) for value in values]
    total = sum(exps)
    if total == 0.0:
        return [0.0 for _ in values]
    return [value / total for value in exps]


def _entailment_index(model: Any) -> int:
    """Find the entailment label index in the model's config, defaulting to 1.

    ``cross-encoder/nli-deberta-v3-small`` maps ``{0: contradiction, 1: entailment,
    2: neutral}``, but the index is read from ``config.id2label`` so a swapped
    model still decides correctly.
    """
    config = getattr(model, "config", None)
    id2label = getattr(config, "id2label", None)
    if isinstance(id2label, Mapping):
        for key, label in id2label.items():
            if isinstance(label, str) and "entail" in label.lower():
                try:
                    return int(key)
                except (TypeError, ValueError):
                    continue
    return 1


class LocalEntailmentScorer:
    """The default local scorer: a lazy cross-encoder NLI model with a fallback.

    Construction records the model id and nothing else. The first scoring call
    imports ``sentence_transformers`` and loads the model with
    ``local_files_only=True``; if that fails for any reason the scorer logs once
    and delegates to :class:`LexicalOverlapScorer` for the rest of the run. A
    failed prediction (rather than a failed load) falls back for that claim only.

    ``model_factory`` is the test seam: tests inject a fake cross-encoder so the
    model path is exercised without loading anything.
    """

    version = SCORER_VERSION

    def __init__(
        self,
        model_id: str = DEFAULT_NLI_MODEL,
        *,
        model_factory: Callable[[], Any] | None = None,
        fallback: EntailmentScorer | None = None,
        entailment_threshold: float = 0.5,
    ) -> None:
        if not 0.0 < entailment_threshold <= 1.0:
            raise ValueError(f"entailment_threshold must be in (0, 1], got {entailment_threshold}")
        self.model_id = model_id
        self.entailment_threshold = entailment_threshold
        if model_factory is not None:
            self._model_factory = model_factory
        else:
            self._model_factory = self._load_cross_encoder
        self._fallback = fallback if fallback is not None else LexicalOverlapScorer()
        self._model: Any | None = None
        self._load_attempted = False

    def _load_cross_encoder(self) -> Any:
        """Import sentence-transformers and load the NLI model, cache-only.

        The import is deliberately function-local: importing this module must not
        import torch, and no code path may download a model implicitly (SPEC
        assumption A6; Locked intent #12).
        """
        from sentence_transformers import CrossEncoder

        return CrossEncoder(self.model_id, local_files_only=True)

    def _ensure_model(self) -> Any | None:
        """Return the loaded model, attempting the load once; ``None`` means fallback."""
        if self._model is not None:
            return self._model
        if self._load_attempted:
            return None

        self._load_attempted = True
        try:
            self._model = self._model_factory()
        except Exception as exc:  # noqa: BLE001 - any load failure means fallback, not a crash
            logger.info(
                "entailment model %s is unavailable (%s); using lexical overlap",
                self.model_id,
                exc,
            )
            self._model = None

        if self._model is None:
            logger.info(
                "entailment model %s is unavailable; using lexical overlap", self.model_id
            )
        return self._model

    @property
    def backend(self) -> str:
        """``"nli"``, ``"lexical"`` (after a failed load) or ``"unresolved"``."""
        if self._model is not None:
            return "nli"
        if self._load_attempted:
            return "lexical"
        return "unresolved"

    @property
    def id(self) -> str:
        """The identity to persist; reflects the judge that actually runs.

        Before the first scoring call the intended NLI identity is reported. Read
        it after scoring to record a fallback run under the lexical scorer, so a
        fallback is never charted as comparable with a model-backed run.
        """
        if self.backend == "lexical":
            return LEXICAL_SCORER_ID
        return f"{NLI_SCORER_ID}:{self.model_id}"

    def supports(self, claim: str, context: str) -> bool:
        model = self._ensure_model()
        if model is None:
            return self._fallback.supports(claim, context)

        try:
            return self._model_supports(model, claim, context)
        except Exception as exc:  # noqa: BLE001 - a model failure must not abort an eval
            logger.warning(
                "entailment model %s failed on a claim (%s); using lexical overlap",
                self.model_id,
                exc,
            )
            return self._fallback.supports(claim, context)

    def _model_supports(self, model: Any, claim: str, context: str) -> bool:
        """One NLI judgement: entailment probability at or above the threshold."""
        raw = model.predict([(context, claim)])
        row = [float(value) for value in raw[0]]
        if len(row) < 2:
            raise ValueError(f"expected per-label scores, got {row!r}")

        index = _entailment_index(model)
        if index >= len(row):
            raise ValueError(f"entailment label {index} is outside scores {row!r}")

        probabilities = _softmax(row)
        return probabilities[index] >= self.entailment_threshold

    def supported(self, claim: str, context: str) -> bool:
        """Alias for :meth:`supports` (the name used by the task plan)."""
        return self.supports(claim, context)


__all__ = [
    "DEFAULT_NLI_MODEL",
    "LEXICAL_SCORER_ID",
    "NLI_SCORER_ID",
    "SCORER_VERSION",
    "EntailmentScorer",
    "FakeEntailmentScorer",
    "LexicalOverlapScorer",
    "LocalEntailmentScorer",
    "PageCitation",
    "TextChunk",
    "evidence_chunks",
    "select_context",
]
