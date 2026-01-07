"""Ensure publication logs are unique for unscheduled publishes."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_publication_logs_unscheduled"
down_revision: str | None = "0008_usage_counters"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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
