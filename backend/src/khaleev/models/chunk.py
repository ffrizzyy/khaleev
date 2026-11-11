"""The ``chunks`` table: one row per retrievable text chunk of a page.

Every chunk keeps the 1-based ``page_number`` it came from, which is what makes
page-level citations and hit-rate@k possible (Locked intent #2).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from khaleev.models.base import Base

if TYPE_CHECKING:
    from khaleev.models.document import Document


class Chunk(Base):
    """A chunk of one PDF page, addressable through ``embedding_ref``."""

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(nullable=False)
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Filled once the chunk lands in the vector index; nullable until then.
    embedding_ref: Mapped[str | None] = mapped_column(nullable=True)

    document: Mapped[Document] = relationship(back_populates="chunks")
