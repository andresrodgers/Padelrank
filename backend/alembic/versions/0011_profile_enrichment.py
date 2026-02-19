"""profile enrichment fields

Revision ID: 0011_profile_enrichment
Revises: 0010_auth_core
Create Date: 2026-02-19
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_profile_enrichment"
down_revision = "0010_auth_core"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user_profiles", sa.Column("country", sa.Text(), nullable=False, server_default="CO"))
    op.add_column("user_profiles", sa.Column("city", sa.Text(), nullable=True))
    op.add_column("user_profiles", sa.Column("handedness", sa.Text(), nullable=False, server_default="U"))
    op.add_column("user_profiles", sa.Column("preferred_side", sa.Text(), nullable=False, server_default="U"))
    op.add_column("user_profiles", sa.Column("birthdate", sa.Date(), nullable=True))
    op.add_column("user_profiles", sa.Column("first_name", sa.Text(), nullable=True))
    op.add_column("user_profiles", sa.Column("last_name", sa.Text(), nullable=True))

    op.execute("ALTER TABLE user_profiles DROP CONSTRAINT IF EXISTS ck_user_profiles_handedness;")
    op.execute("""
        ALTER TABLE user_profiles
        ADD CONSTRAINT ck_user_profiles_handedness
        CHECK (handedness IN ('R','L','U'));
    """)
    op.execute("ALTER TABLE user_profiles DROP CONSTRAINT IF EXISTS ck_user_profiles_preferred_side;")
    op.execute("""
        ALTER TABLE user_profiles
        ADD CONSTRAINT ck_user_profiles_preferred_side
        CHECK (preferred_side IN ('drive','reves','both','U'));
    """)


def downgrade():
    op.execute("ALTER TABLE user_profiles DROP CONSTRAINT IF EXISTS ck_user_profiles_preferred_side;")
    op.execute("ALTER TABLE user_profiles DROP CONSTRAINT IF EXISTS ck_user_profiles_handedness;")
    op.drop_column("user_profiles", "last_name")
    op.drop_column("user_profiles", "first_name")
    op.drop_column("user_profiles", "birthdate")
    op.drop_column("user_profiles", "preferred_side")
    op.drop_column("user_profiles", "handedness")
    op.drop_column("user_profiles", "city")
    op.drop_column("user_profiles", "country")
