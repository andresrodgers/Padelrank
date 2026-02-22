"""expand user status lifecycle states

Revision ID: 0019_user_status_lifecycle
Revises: 0018_rivio_foundations
Create Date: 2026-02-22
"""

from alembic import op


revision = "0019_user_status_lifecycle"
down_revision = "0018_rivio_foundations"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_user_status", "users", type_="check")
    op.create_check_constraint(
        "ck_user_status",
        "users",
        "status in ('active','blocked','pending_deletion','deleted')",
    )


def downgrade():
    op.execute(
        """
        UPDATE users
        SET status='blocked'
        WHERE status IN ('pending_deletion','deleted')
        """
    )
    op.drop_constraint("ck_user_status", "users", type_="check")
    op.create_check_constraint("ck_user_status", "users", "status in ('active','blocked')")
