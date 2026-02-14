"""init p0 schema

Revision ID: 0001_init_p0
Revises: 
Create Date: 2026-02-11

"""
from alembic import op
import sqlalchemy as sa

revision = "0001_init_p0"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # users
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("phone_e164", sa.Text, nullable=False, unique=True),
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status in ('active','blocked')", name="ck_user_status"),
    )

    # auth_otps (simple)
    op.create_table(
        "auth_otps",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("phone_e164", sa.Text, nullable=False),
        sa.Column("code_hash", sa.Text, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_auth_otps_phone_expires", "auth_otps", ["phone_e164", "expires_at"])

    # user_profiles
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("alias", sa.Text, nullable=False, unique=True),
        sa.Column("gender", sa.Text, nullable=False),
        sa.Column("is_public", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("gender in ('M','F')", name="ck_profile_gender"),
    )

    # ladders
    op.create_table(
        "ladders",
        sa.Column("code", sa.Text, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
    )

    # categories
    op.create_table(
        "categories",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("ladder_code", sa.Text, sa.ForeignKey("ladders.code", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="1"),
        sa.UniqueConstraint("ladder_code", "code", name="uq_category_ladder_code"),
    )

    # clubs
    op.create_table(
        "clubs",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("city", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
    )

    # user_ladder_state
    op.create_table(
        "user_ladder_state",
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("ladder_code", sa.Text, sa.ForeignKey("ladders.code", ondelete="CASCADE"), primary_key=True),
        sa.Column("category_id", sa.Uuid, sa.ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("rating", sa.Integer, nullable=False, server_default="1000"),
        sa.Column("verified_matches", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_provisional", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("trust_score", sa.Integer, nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_user_ladder_user", "user_ladder_state", ["user_id"])
    op.create_index("ix_user_ladder_rank", "user_ladder_state", ["ladder_code", "category_id", sa.text("rating DESC")])

    # matches
    op.create_table(
        "matches",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("ladder_code", sa.Text, sa.ForeignKey("ladders.code", ondelete="RESTRICT"), nullable=False),
        sa.Column("category_id", sa.Uuid, sa.ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("club_id", sa.Uuid, sa.ForeignKey("clubs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("played_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="pending_confirm"),
        sa.Column("confirmation_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_count", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("has_dispute", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("rank_processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("anti_farming_weight", sa.Numeric(4,2), nullable=False, server_default="1.00"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status in ('pending_confirm','verified','disputed','expired','void')", name="ck_match_status"),
    )
    op.create_index("ix_matches_creator_status_deadline", "matches", ["created_by", "status", "confirmation_deadline"])
    op.create_index("ix_matches_ladder_cat_status_played", "matches", ["ladder_code", "category_id", "status", sa.text("played_at DESC")])

    # match_participants
    op.create_table(
        "match_participants",
        sa.Column("match_id", sa.Uuid, sa.ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("team_no", sa.SmallInteger, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("team_no in (1,2)", name="ck_team_no"),
    )
    op.create_index("ix_match_participants_match", "match_participants", ["match_id"])

    # match_scores
    op.create_table(
        "match_scores",
        sa.Column("match_id", sa.Uuid, sa.ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("score_json", sa.JSON, nullable=False),
        sa.Column("winner_team_no", sa.SmallInteger, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("winner_team_no in (1,2)", name="ck_winner_team_no"),
    )

    # match_confirmations
    op.create_table(
        "match_confirmations",
        sa.Column("match_id", sa.Uuid, sa.ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("source", sa.Text, nullable=True),
        sa.CheckConstraint("status in ('pending','confirmed','disputed')", name="ck_confirmation_status"),
    )
    op.create_index("ix_match_confirmations_user_status", "match_confirmations", ["user_id", "status"])
    op.create_index("ix_match_confirmations_match_status", "match_confirmations", ["match_id", "status"])

    # match_disputes
    op.create_table(
        "match_disputes",
        sa.Column("match_id", sa.Uuid, sa.ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("opened_by", sa.Uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reason_code", sa.Text, nullable=False),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("status", sa.Text, nullable=False, server_default="open"),
        sa.CheckConstraint("status in ('open')", name="ck_dispute_status"),
    )

    # rating_events
    op.create_table(
        "rating_events",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("match_id", sa.Uuid, sa.ForeignKey("matches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ladder_code", sa.Text, nullable=False),
        sa.Column("category_id", sa.Uuid, nullable=False),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("old_rating", sa.Integer, nullable=False),
        sa.Column("new_rating", sa.Integer, nullable=False),
        sa.Column("delta", sa.Integer, nullable=False),
        sa.Column("k_factor", sa.Integer, nullable=False),
        sa.Column("weight", sa.Numeric(4,2), nullable=False, server_default="1.00"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_rating_events_user_created", "rating_events", ["user_id", sa.text("created_at DESC")])
    op.create_index("ix_rating_events_match", "rating_events", ["match_id"])

    # audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("actor_user_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("entity_type", sa.Text, nullable=False),
        sa.Column("entity_id", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("data", sa.JSON, nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_audit_entity", "audit_log", ["entity_type", "entity_id"])
    op.create_index("ix_audit_actor_created", "audit_log", ["actor_user_id", sa.text("created_at DESC")])

    # Seed ladders + categories + clubs (placeholders)
    op.execute("""
        INSERT INTO ladders (code, name, is_active) VALUES
          ('HM','Hombres', true),
          ('WM','Mujeres', true),
          ('MX','Mixtos', true)
        ON CONFLICT (code) DO NOTHING;
    """)

    op.execute("""
        INSERT INTO categories (ladder_code, code, name, sort_order)
        VALUES
          ('HM','C1','Categoría 1',1),
          ('HM','C2','Categoría 2',2),
          ('HM','C3','Categoría 3',3),
          ('WM','C1','Categoría 1',1),
          ('WM','C2','Categoría 2',2),
          ('WM','C3','Categoría 3',3),
          ('MX','C1','Categoría 1',1),
          ('MX','C2','Categoría 2',2),
          ('MX','C3','Categoría 3',3)
        ON CONFLICT (ladder_code, code) DO NOTHING;
    """)

    op.execute("""
        INSERT INTO clubs (name, city, is_active) VALUES
          ('Club A', 'Neiva', true),
          ('Club B', 'Neiva', true),
          ('Club C', 'Neiva', true);
    """)

def downgrade():
    op.drop_index("ix_audit_actor_created", table_name="audit_log")
    op.drop_index("ix_audit_entity", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index("ix_rating_events_match", table_name="rating_events")
    op.drop_index("ix_rating_events_user_created", table_name="rating_events")
    op.drop_table("rating_events")

    op.drop_table("match_disputes")

    op.drop_index("ix_match_confirmations_match_status", table_name="match_confirmations")
    op.drop_index("ix_match_confirmations_user_status", table_name="match_confirmations")
    op.drop_table("match_confirmations")

    op.drop_table("match_scores")

    op.drop_index("ix_match_participants_match", table_name="match_participants")
    op.drop_table("match_participants")

    op.drop_index("ix_matches_ladder_cat_status_played", table_name="matches")
    op.drop_index("ix_matches_creator_status_deadline", table_name="matches")
    op.drop_table("matches")

    op.drop_index("ix_user_ladder_rank", table_name="user_ladder_state")
    op.drop_index("ix_user_ladder_user", table_name="user_ladder_state")
    op.drop_table("user_ladder_state")

    op.drop_table("clubs")
    op.drop_table("categories")
    op.drop_table("ladders")

    op.drop_table("user_profiles")
    op.drop_index("ix_auth_otps_phone_expires", table_name="auth_otps")
    op.drop_table("auth_otps")
    op.drop_table("users")
