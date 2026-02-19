"""user contact change otp flow

Revision ID: 0009_user_contact_change
Revises: 0008_email_contact_auth
Create Date: 2026-02-19
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_user_contact_change"
down_revision = "0008_email_contact_auth"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_contact_changes",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_kind", sa.Text, nullable=False),
        sa.Column("new_contact_value", sa.Text, nullable=False),
        sa.Column("code_hash", sa.Text, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("contact_kind in ('phone','email')", name="ck_user_contact_change_kind"),
    )
    op.create_index(
        "ix_user_contact_changes_user_kind_created",
        "user_contact_changes",
        ["user_id", "contact_kind", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_user_contact_changes_kind_value_created",
        "user_contact_changes",
        ["contact_kind", "new_contact_value", sa.text("created_at DESC")],
    )


def downgrade():
    op.drop_index("ix_user_contact_changes_kind_value_created", table_name="user_contact_changes")
    op.drop_index("ix_user_contact_changes_user_kind_created", table_name="user_contact_changes")
    op.drop_table("user_contact_changes")
