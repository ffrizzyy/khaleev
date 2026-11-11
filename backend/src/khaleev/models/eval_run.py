"""The ``eval_runs`` and ``eval_run_entries`` tables.

An eval run persists both aggregate metrics and one row per golden entry so the
dashboard can show history and per-entry results without recomputing anything
(SPEC F5, Boundaries -> Always "persist eval runs").
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from khaleev.models.base import Base, utcnow

if TYPE_CHECKING:
    from khaleev.models.document import Document


class EvalRun(Base):
    """One eval run over one document's golden set.

    ``hit_rate`` and ``faithfulness`` are floats in ``[0.0, 1.0]`` (Metric
    definitions); ``config`` holds the golden-set revision and scorer version
    needed for run comparability (AC10).
    """

    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    k: Mapped[int] = mapped_column(nullable=False)
    embedder_id: Mapped[str] = mapped_column(nullable=False)
    scorer_id: Mapped[str] = mapped_column(nullable=False)
    hit_rate: Mapped[float] = mapped_column(Float, nullable=False)
    faithfulness: Mapped[float] = mapped_column(Float, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    document: Mapped[Document] = relationship(back_populates="eval_runs")
    entries: Mapped[list[EvalRunEntry]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="EvalRunEntry.golden_index",
    )


class EvalRunEntry(Base):
    """The persisted result of one golden entry inside an eval run."""

    __tablename__ = "eval_run_entries"

    run_id: Mapped[int] = mapped_column(
        ForeignKey("eval_runs.id", ondelete="CASCADE"), primary_key=True
    )
    golden_index: Mapped[int] = mapped_column(primary_key=True)
    hit: Mapped[bool] = mapped_column(Boolean, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    claims: Mapped[int] = mapped_column(nullable=False)
    supported_claims: Mapped[int] = mapped_column(nullable=False)
    faithfulness: Mapped[float] = mapped_column(Float, nullable=False)

    run: Mapped[EvalRun] = relationship(back_populates="entries")
