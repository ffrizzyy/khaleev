"""ORM models for the Khaleev database.

Importing this package registers every table on ``Base.metadata``, which is what
both ``Base.metadata.create_all`` and Alembic's ``target_metadata`` need.
"""

from __future__ import annotations

from khaleev.models.base import Base
from khaleev.models.chunk import Chunk
from khaleev.models.document import Document
from khaleev.models.eval_run import EvalRun, EvalRunEntry
from khaleev.models.golden import GoldenSet

__all__ = ["Base", "Chunk", "Document", "EvalRun", "EvalRunEntry", "GoldenSet"]
