"""Add post_drafts table."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_post_drafts"
down_revision: str | None = "0003_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("source_items", sa.Column("facts_cache", sa.Text(), nullable=True))
    op.create_table(
        "post_drafts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("source_item_id", sa.Integer(), sa.ForeignKey("source_items.id"), nullable=False),
        sa.Column("template_id", sa.String(length=128), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("draft_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="new"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("draft_hash", name="uq_post_drafts_hash"),
    )


def downgrade() -> None:
    op.drop_column("source_items", "facts_cache")
    op.drop_table("post_drafts")
