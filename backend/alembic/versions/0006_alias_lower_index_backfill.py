"""add alias lower unique index backfill

Revision ID: 0006_alias_lower_index_backfill
Revises: 0005_allow_u_gender
Create Date: 2026-02-19
"""

from alembic import op


revision = "0006_alias_lower_index_backfill"
down_revision = "0005_allow_u_gender"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM user_profiles
                GROUP BY lower(alias)
                HAVING COUNT(*) > 1
            ) THEN
                RAISE EXCEPTION 'Cannot enforce unique lower(alias): duplicate aliases exist.';
            END IF;
        END $$;
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_user_profiles_alias_lower
        ON user_profiles (lower(alias));
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_user_profiles_alias_lower;")
