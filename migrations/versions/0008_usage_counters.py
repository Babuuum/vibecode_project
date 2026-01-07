"""Add usage counters."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0008_usage_counters"
down_revision: Union[str, None] = "0007_schedule"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usage_counters",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("drafts_generated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("posts_published", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("llm_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_est", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("project_id", "day", name="uq_usage_project_day"),
    )


def downgrade() -> None:
    op.drop_table("usage_counters")
