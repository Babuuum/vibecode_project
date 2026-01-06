"""Add schedules and publication log idempotency."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0007_schedule"
down_revision: Union[str, None] = "0006_source_failures"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "schedules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("tz", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("slots_json", sa.Text(), nullable=False),
        sa.Column("per_day_limit", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint("project_id", name="uq_schedules_project"),
    )

    with op.batch_alter_table("publication_logs") as batch_op:
        batch_op.drop_constraint("uq_publication_draft", type_="unique")
        batch_op.create_unique_constraint(
            "uq_publication_draft_scheduled", ["draft_id", "scheduled_at"]
        )


def downgrade() -> None:
    with op.batch_alter_table("publication_logs") as batch_op:
        batch_op.drop_constraint("uq_publication_draft_scheduled", type_="unique")
        batch_op.create_unique_constraint("uq_publication_draft", ["draft_id"])

    op.drop_table("schedules")
