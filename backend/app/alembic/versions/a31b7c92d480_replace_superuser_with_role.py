"""Replace is_superuser with role.

Revision ID: a31b7c92d480
Revises: fe56fa70289e
"""
from alembic import op
import sqlalchemy as sa

revision = "a31b7c92d480"
down_revision = "fe56fa70289e"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user", sa.Column("role", sa.String(7), nullable=False, server_default="member"))
    op.execute("UPDATE \"user\" SET role = 'admin' WHERE is_superuser = true")
    op.create_check_constraint("user_role", "user", "role IN ('admin', 'manager', 'member')")
    op.drop_column("user", "is_superuser")


def downgrade():
    # Managers become ordinary users: the old schema has only two access levels.
    op.add_column("user", sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("UPDATE \"user\" SET is_superuser = true WHERE role = 'admin'")
    op.drop_constraint("user_role", "user", type_="check")
    op.drop_column("user", "role")
