"""基线 schema：与 ORM create_all 对齐，并启用 pgvector 扩展。

Revision ID: 001_baseline
Revises:
Create Date: 2026-05-25

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 业务表由 SQLAlchemy metadata 生成；此处仅补向量表（PostgreSQL 专用）
    if bind.dialect.name == "postgresql":
        op.create_table(
            "evidence_vectors",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "chunk_id",
                sa.String(36),
                sa.ForeignKey("evidence_chunks.id", ondelete="CASCADE"),
                nullable=False,
                unique=True,
            ),
            sa.Column("task_id", sa.String(36), nullable=False, index=True),
            sa.Column("source_id", sa.String(36), nullable=False),
            sa.Column("embedding", sa.Text(), nullable=False),
            sa.Column("dimension", sa.Integer(), nullable=False),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
        )
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_evidence_vectors_task_id
            ON evidence_vectors (task_id)
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_table("evidence_vectors")
