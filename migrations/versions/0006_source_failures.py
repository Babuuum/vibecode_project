"""Add source failure tracking."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0006_source_failures"
down_revision: Union[str, None] = "0005_publication_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("sources", "consecutive_failures")
