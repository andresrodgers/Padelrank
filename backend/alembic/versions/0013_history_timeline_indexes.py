"""history timeline indexes

Revision ID: 0013_history_timeline_indexes
Revises: 0012_ranking_location_indexes
Create Date: 2026-02-21
"""

from alembic import op


revision = "0013_history_timeline_indexes"
down_revision = "0012_ranking_location_indexes"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_match_participants_user_match
        ON match_participants (user_id, match_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_matches_status_played_created
        ON matches (status, played_at DESC, created_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_matches_club_played
        ON matches (club_id, played_at DESC)
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_matches_club_played")
    op.execute("DROP INDEX IF EXISTS ix_matches_status_played_created")
    op.execute("DROP INDEX IF EXISTS ix_match_participants_user_match")
