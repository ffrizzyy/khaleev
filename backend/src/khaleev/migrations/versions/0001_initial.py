"""Initial Khaleev schema: documents, chunks, golden sets and eval history.

Revision ID: 0001
Revises:
Create Date: 2026-11-11

This is the only schema migration the plan allows without asking first (SPEC
Boundaries -> Ask first). Every column below is exactly a column from the SPEC
data model; `tests/unit/test_migrations.py` compares this migrated database to
`Base.metadata` so the two can never drift.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        sa.UniqueConstraint("content_hash", name=op.f("uq_documents_content_hash")),
    )

    op.create_table(
        "chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding_ref", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_chunks_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunks")),
    )
    op.create_index(op.f("ix_chunks_document_id"), "chunks", ["document_id"])

    op.create_table(
        "golden_sets",
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("entries", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_golden_sets_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("document_id", name=op.f("pk_golden_sets")),
    )

    op.create_table(
        "eval_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("k", sa.Integer(), nullable=False),
        sa.Column("embedder_id", sa.String(), nullable=False),
        sa.Column("scorer_id", sa.String(), nullable=False),
        sa.Column("hit_rate", sa.Float(), nullable=False),
        sa.Column("faithfulness", sa.Float(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_eval_runs_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eval_runs")),
    )
    op.create_index(op.f("ix_eval_runs_document_id"), "eval_runs", ["document_id"])

    op.create_table(
        "eval_run_entries",
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("golden_index", sa.Integer(), nullable=False),
        sa.Column("hit", sa.Boolean(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("claims", sa.Integer(), nullable=False),
        sa.Column("supported_claims", sa.Integer(), nullable=False),
        sa.Column("faithfulness", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["eval_runs.id"],
            name=op.f("fk_eval_run_entries_run_id_eval_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("run_id", "golden_index", name=op.f("pk_eval_run_entries")),
    )


def downgrade() -> None:
    op.drop_table("eval_run_entries")
    op.drop_index(op.f("ix_eval_runs_document_id"), table_name="eval_runs")
    op.drop_table("eval_runs")
    op.drop_table("golden_sets")
    op.drop_index(op.f("ix_chunks_document_id"), table_name="chunks")
    op.drop_table("chunks")
    op.drop_table("documents")
