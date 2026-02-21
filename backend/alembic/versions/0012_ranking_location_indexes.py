"""ranking location indexes

Revision ID: 0012_ranking_location_indexes
Revises: 0011_profile_enrichment
Create Date: 2026-02-20
"""

from alembic import op


revision = "0012_ranking_location_indexes"
down_revision = "0011_profile_enrichment"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_user_profiles_country_public_user
        ON user_profiles (country, user_id)
        WHERE is_public = true
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_user_profiles_country_city_public_user
        ON user_profiles (country, lower(city), user_id)
        WHERE is_public = true AND city IS NOT NULL
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_user_profiles_country_city_public_user")
    op.execute("DROP INDEX IF EXISTS ix_user_profiles_country_public_user")
