"""analytics kpis and series read model

Revision ID: 0017_analytics_kpis_and_series
Revises: 0016_auth_retention_indexes
Create Date: 2026-02-21
"""

from alembic import op
import sqlalchemy as sa


revision = "0017_analytics_kpis_and_series"
down_revision = "0016_auth_retention_indexes"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user_analytics_state", sa.Column("rolling_bits_50", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("user_analytics_state", sa.Column("rolling_size_50", sa.SmallInteger(), nullable=False, server_default="0"))
    op.add_column("user_analytics_state", sa.Column("rolling_5_win_rate", sa.Numeric(5, 2), nullable=False, server_default="0.00"))
    op.add_column("user_analytics_state", sa.Column("rolling_20_win_rate", sa.Numeric(5, 2), nullable=False, server_default="0.00"))
    op.add_column("user_analytics_state", sa.Column("rolling_50_win_rate", sa.Numeric(5, 2), nullable=False, server_default="0.00"))
    op.add_column("user_analytics_state", sa.Column("matches_7d", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("user_analytics_state", sa.Column("matches_30d", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("user_analytics_state", sa.Column("matches_90d", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("user_analytics_state", sa.Column("close_matches", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("user_analytics_state", sa.Column("close_match_rate", sa.Numeric(5, 2), nullable=False, server_default="0.00"))
    op.add_column("user_analytics_state", sa.Column("vs_stronger_matches", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("user_analytics_state", sa.Column("vs_stronger_wins", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("user_analytics_state", sa.Column("vs_stronger_win_rate", sa.Numeric(5, 2), nullable=False, server_default="0.00"))
    op.add_column("user_analytics_state", sa.Column("vs_similar_matches", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("user_analytics_state", sa.Column("vs_similar_wins", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("user_analytics_state", sa.Column("vs_similar_win_rate", sa.Numeric(5, 2), nullable=False, server_default="0.00"))
    op.add_column("user_analytics_state", sa.Column("vs_weaker_matches", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("user_analytics_state", sa.Column("vs_weaker_wins", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("user_analytics_state", sa.Column("vs_weaker_win_rate", sa.Numeric(5, 2), nullable=False, server_default="0.00"))

    op.add_column("user_analytics_match_applied", sa.Column("is_close_match", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("user_analytics_match_applied", sa.Column("teammate_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    op.add_column("user_analytics_match_applied", sa.Column("opponent_a_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    op.add_column("user_analytics_match_applied", sa.Column("opponent_b_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    op.add_column("user_analytics_match_applied", sa.Column("opponent_avg_rating", sa.Integer(), nullable=True))
    op.add_column("user_analytics_match_applied", sa.Column("quality_bucket", sa.Text(), nullable=False, server_default="similar"))
    op.add_column("user_analytics_match_applied", sa.Column("rating_before", sa.Integer(), nullable=True))
    op.add_column("user_analytics_match_applied", sa.Column("rating_after", sa.Integer(), nullable=True))
    op.add_column("user_analytics_match_applied", sa.Column("rating_delta", sa.Integer(), nullable=True))
    op.add_column("user_analytics_match_applied", sa.Column("rolling_10_win_rate", sa.Numeric(5, 2), nullable=True))
    op.add_column("user_analytics_match_applied", sa.Column("rolling_20_win_rate", sa.Numeric(5, 2), nullable=True))
    op.add_column("user_analytics_match_applied", sa.Column("rolling_50_win_rate", sa.Numeric(5, 2), nullable=True))
    op.add_column("user_analytics_match_applied", sa.Column("streak_type_after", sa.Text(), nullable=True))
    op.add_column("user_analytics_match_applied", sa.Column("streak_len_after", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_user_analytics_quality_bucket",
        "user_analytics_match_applied",
        "quality_bucket IN ('stronger','similar','weaker')",
    )
    op.create_check_constraint(
        "ck_user_analytics_streak_after",
        "user_analytics_match_applied",
        "streak_type_after IN ('W','L') OR streak_type_after IS NULL",
    )
    op.create_index(
        "ix_user_analytics_applied_user_ladder_quality",
        "user_analytics_match_applied",
        ["user_id", "ladder_code", "quality_bucket"],
    )
    op.create_index(
        "ix_user_analytics_applied_user_ladder_partner",
        "user_analytics_match_applied",
        ["user_id", "ladder_code", "teammate_user_id"],
    )
    op.create_index(
        "ix_user_analytics_applied_user_ladder_rating",
        "user_analytics_match_applied",
        ["user_id", "ladder_code", sa.text("played_at DESC"), "rating_after"],
    )

    op.create_table(
        "user_analytics_partner_stats",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("ladder_code", sa.Text(), sa.ForeignKey("ladders.code", ondelete="CASCADE"), primary_key=True),
        sa.Column("partner_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("matches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("wins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("losses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("win_rate", sa.Numeric(5, 2), nullable=False, server_default="0.00"),
        sa.Column("last_played_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_user_analytics_partner_top",
        "user_analytics_partner_stats",
        ["user_id", "ladder_code", sa.text("matches DESC"), sa.text("win_rate DESC")],
    )

    op.create_table(
        "user_analytics_rival_stats",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("ladder_code", sa.Text(), sa.ForeignKey("ladders.code", ondelete="CASCADE"), primary_key=True),
        sa.Column("rival_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("matches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("wins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("losses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("win_rate", sa.Numeric(5, 2), nullable=False, server_default="0.00"),
        sa.Column("last_played_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_user_analytics_rival_top",
        "user_analytics_rival_stats",
        ["user_id", "ladder_code", sa.text("matches DESC"), sa.text("win_rate DESC")],
    )


def downgrade():
    op.drop_index("ix_user_analytics_rival_top", table_name="user_analytics_rival_stats")
    op.drop_table("user_analytics_rival_stats")

    op.drop_index("ix_user_analytics_partner_top", table_name="user_analytics_partner_stats")
    op.drop_table("user_analytics_partner_stats")

    op.drop_index("ix_user_analytics_applied_user_ladder_rating", table_name="user_analytics_match_applied")
    op.drop_index("ix_user_analytics_applied_user_ladder_partner", table_name="user_analytics_match_applied")
    op.drop_index("ix_user_analytics_applied_user_ladder_quality", table_name="user_analytics_match_applied")
    op.drop_constraint("ck_user_analytics_streak_after", "user_analytics_match_applied", type_="check")
    op.drop_constraint("ck_user_analytics_quality_bucket", "user_analytics_match_applied", type_="check")
    op.drop_column("user_analytics_match_applied", "streak_len_after")
    op.drop_column("user_analytics_match_applied", "streak_type_after")
    op.drop_column("user_analytics_match_applied", "rolling_50_win_rate")
    op.drop_column("user_analytics_match_applied", "rolling_20_win_rate")
    op.drop_column("user_analytics_match_applied", "rolling_10_win_rate")
    op.drop_column("user_analytics_match_applied", "rating_delta")
    op.drop_column("user_analytics_match_applied", "rating_after")
    op.drop_column("user_analytics_match_applied", "rating_before")
    op.drop_column("user_analytics_match_applied", "quality_bucket")
    op.drop_column("user_analytics_match_applied", "opponent_avg_rating")
    op.drop_column("user_analytics_match_applied", "opponent_b_user_id")
    op.drop_column("user_analytics_match_applied", "opponent_a_user_id")
    op.drop_column("user_analytics_match_applied", "teammate_user_id")
    op.drop_column("user_analytics_match_applied", "is_close_match")

    op.drop_column("user_analytics_state", "vs_weaker_win_rate")
    op.drop_column("user_analytics_state", "vs_weaker_wins")
    op.drop_column("user_analytics_state", "vs_weaker_matches")
    op.drop_column("user_analytics_state", "vs_similar_win_rate")
    op.drop_column("user_analytics_state", "vs_similar_wins")
    op.drop_column("user_analytics_state", "vs_similar_matches")
    op.drop_column("user_analytics_state", "vs_stronger_win_rate")
    op.drop_column("user_analytics_state", "vs_stronger_wins")
    op.drop_column("user_analytics_state", "vs_stronger_matches")
    op.drop_column("user_analytics_state", "close_match_rate")
    op.drop_column("user_analytics_state", "close_matches")
    op.drop_column("user_analytics_state", "matches_90d")
    op.drop_column("user_analytics_state", "matches_30d")
    op.drop_column("user_analytics_state", "matches_7d")
    op.drop_column("user_analytics_state", "rolling_50_win_rate")
    op.drop_column("user_analytics_state", "rolling_20_win_rate")
    op.drop_column("user_analytics_state", "rolling_5_win_rate")
    op.drop_column("user_analytics_state", "rolling_size_50")
    op.drop_column("user_analytics_state", "rolling_bits_50")
