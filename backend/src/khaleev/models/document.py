"""The ``documents`` table: one row per unique uploaded PDF.

Deleting a document must remove its chunks, golden set and eval history (AC11),
so every child table points here with ``ON DELETE CASCADE``.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from khaleev.models.base import Base, utcnow

if TYPE_CHECKING:
    from khaleev.models.chunk import Chunk
    from khaleev.models.eval_run import EvalRun
    from khaleev.models.golden import GoldenSet


class Document(Base):
    """An ingested PDF; ``content_hash`` is the dedupe key for re-uploads."""

    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("content_hash", name="uq_documents_content_hash"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    content_hash: Mapped[str] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(nullable=False)
    page_count: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    golden_set: Mapped[GoldenSet | None] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    eval_runs: Mapped[list[EvalRun]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
