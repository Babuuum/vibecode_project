"""Add sources and source_items."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003_sources"
down_revision: Union[str, None] = "0002_channel_binding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False, server_default="rss"),
        sa.Column("url", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("fetch_interval_min", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("last_fetch_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.UniqueConstraint("project_id", "url", name="uq_sources_project_url"),
    )

    op.create_table(
        "source_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("external_id", sa.String(length=512), nullable=False),
        sa.Column("link", sa.String(length=1024), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="new"),
        sa.UniqueConstraint("source_id", "external_id", name="uq_source_items_external"),
        sa.UniqueConstraint("source_id", "link", name="uq_source_items_link"),
    )


def downgrade() -> None:
    op.drop_table("source_items")
    op.drop_table("sources")
