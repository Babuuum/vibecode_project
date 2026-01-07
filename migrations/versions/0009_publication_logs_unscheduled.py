"""Ensure publication logs are unique for unscheduled publishes."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0009_publication_logs_unscheduled"
down_revision: Union[str, None] = "0008_usage_counters"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_publication_draft_unscheduled",
        "publication_logs",
        ["draft_id"],
        unique=True,
        postgresql_where=sa.text("scheduled_at IS NULL"),
        sqlite_where=sa.text("scheduled_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_publication_draft_unscheduled", table_name="publication_logs")
