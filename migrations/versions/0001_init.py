"""Initial schema."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001_init"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tg_id", sa.Integer(), nullable=False, unique=True),
    )

    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("tz", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
    )

    op.create_table(
        "project_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False, unique=True),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("niche", sa.String(length=128), nullable=False),
        sa.Column("tone", sa.String(length=64), nullable=False),
        sa.Column("template_id", sa.String(length=128), nullable=True),
        sa.Column("max_post_len", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("safe_mode", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("autopost_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_table("project_settings")
    op.drop_table("projects")
    op.drop_table("users")
