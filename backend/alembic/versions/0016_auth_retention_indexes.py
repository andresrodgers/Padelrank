"""auth retention indexes

Revision ID: 0016_auth_retention_indexes
Revises: 0015_perf_hardening_indexes
Create Date: 2026-02-21
"""

from alembic import op


revision = "0016_auth_retention_indexes"
down_revision = "0015_perf_hardening_indexes"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_auth_otps_created_at
        ON auth_otps (created_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_auth_login_attempts_created_at
        ON auth_login_attempts (created_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_user_contact_changes_created_at
        ON user_contact_changes (created_at DESC)
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_user_contact_changes_created_at")
    op.execute("DROP INDEX IF EXISTS ix_auth_login_attempts_created_at")
    op.execute("DROP INDEX IF EXISTS ix_auth_otps_created_at")
