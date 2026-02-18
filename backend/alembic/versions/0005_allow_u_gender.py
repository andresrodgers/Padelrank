from alembic import op

revision = "0005_allow_u_gender"
down_revision = "0004_match_score_proposal"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE user_profiles DROP CONSTRAINT IF EXISTS ck_profile_gender;")
    op.execute("""
        ALTER TABLE user_profiles
        ADD CONSTRAINT ck_profile_gender
        CHECK (gender IN ('M','F','U'));
    """)


def downgrade():
    op.execute("ALTER TABLE user_profiles DROP CONSTRAINT IF EXISTS ck_profile_gender;")
    op.execute("""
        ALTER TABLE user_profiles
        ADD CONSTRAINT ck_profile_gender
        CHECK (gender IN ('M','F'));
    """)
