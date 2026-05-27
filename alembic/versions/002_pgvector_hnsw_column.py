"""pgvector 原生向量列 + HNSW 索引。

Revision ID: 002_pgvector_hnsw
Revises: 001_baseline
Create Date: 2026-05-25

"""

from typing import Sequence, Union

from alembic import op

revision: str = "002_pgvector_hnsw"
down_revision: Union[str, None] = "001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        ALTER TABLE evidence_vectors
        ADD COLUMN IF NOT EXISTS embedding_vec vector(1024)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_evidence_vectors_hnsw
        ON evidence_vectors
        USING hnsw (embedding_vec vector_cosine_ops)
        WITH (m = 16, ef_construction = 200)
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_evidence_vectors_hnsw")
    op.execute("ALTER TABLE evidence_vectors DROP COLUMN IF EXISTS embedding_vec")
