"""pgvector HNSW — remove hardcoded vector(1024) dimension constraint.

Revision ID: 003_pgvector_unconstrained_dim
Revises: 002_pgvector_hnsw
Create Date: 2026-05-26

Replaces ``vector(1024)`` with unconstrained ``vector`` so any embedding
dimension (128 from local_hashing, 1024 from dashscope, etc.) works
without a CAST error at write time.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "003_pgvector_unconstrained_dim"
down_revision: Union[str, None] = "002_pgvector_hnsw"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        "ALTER TABLE evidence_vectors "
        "ALTER COLUMN embedding_vec TYPE vector USING embedding_vec::vector"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TABLE evidence_vectors "
        "ALTER COLUMN embedding_vec TYPE vector(1024) USING embedding_vec::vector(1024)"
    )
