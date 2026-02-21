"""perf hardening indexes

Revision ID: 0015_perf_hardening_indexes
Revises: 0014_analytics_read_model
Create Date: 2026-02-21
"""

from alembic import op


revision = "0015_perf_hardening_indexes"
down_revision = "0014_analytics_read_model"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_user_ladder_rank_full
        ON user_ladder_state (ladder_code, category_id, rating DESC, verified_matches DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_matches_verified_played_created
        ON matches (played_at DESC, created_at DESC)
        WHERE status='verified'
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_matches_pending_deadline
        ON matches (confirmation_deadline)
        WHERE status='pending_confirm'
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_matches_pending_deadline")
    op.execute("DROP INDEX IF EXISTS ix_matches_verified_played_created")
    op.execute("DROP INDEX IF EXISTS ix_user_ladder_rank_full")
