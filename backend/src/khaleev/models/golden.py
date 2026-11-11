"""The ``golden_sets`` table: the curated Q&A set of one document.

A document has at most one golden set: the row is keyed by ``document_id``. The
entries live in SQLite as JSON for metrics, while the human-editable file lives
on disk and its path is recorded in ``path`` (Locked intent #8, suggestion).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from khaleev.models.base import Base

if TYPE_CHECKING:
    from khaleev.models.document import Document


class GoldenSet(Base):
    """One revision of a document's golden set and its JSON entries."""

    __tablename__ = "golden_sets"

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    revision: Mapped[str] = mapped_column(nullable=False)
    path: Mapped[str] = mapped_column(nullable=False)
    entries: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)

    document: Mapped[Document] = relationship(back_populates="golden_set")
