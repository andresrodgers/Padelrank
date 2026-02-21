"""analytics read model

Revision ID: 0014_analytics_read_model
Revises: 0013_history_timeline_indexes
Create Date: 2026-02-21
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_analytics_read_model"
down_revision = "0013_history_timeline_indexes"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_analytics_state",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("ladder_code", sa.Text(), sa.ForeignKey("ladders.code", ondelete="CASCADE"), primary_key=True),
        sa.Column("total_verified_matches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("wins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("losses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("win_rate", sa.Numeric(5, 2), nullable=False, server_default="0.00"),
        sa.Column("current_streak_type", sa.Text(), nullable=True),
        sa.Column("current_streak_len", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("best_win_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("best_loss_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recent_form_bits", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("recent_form_size", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("recent_10_matches", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("recent_10_wins", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("recent_10_win_rate", sa.Numeric(5, 2), nullable=False, server_default="0.00"),
        sa.Column("current_rating", sa.Integer(), nullable=True),
        sa.Column("peak_rating", sa.Integer(), nullable=True),
        sa.Column("last_match_id", sa.Uuid(), sa.ForeignKey("matches.id", ondelete="SET NULL"), nullable=True),
        sa.Column("last_match_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("current_streak_type IN ('W','L') OR current_streak_type IS NULL", name="ck_user_analytics_streak_type"),
    )
    op.create_index("ix_user_analytics_user", "user_analytics_state", ["user_id"])
    op.create_index("ix_user_analytics_ladder_rating", "user_analytics_state", ["ladder_code", sa.text("current_rating DESC")])

    op.create_table(
        "user_analytics_match_applied",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("match_id", sa.Uuid(), sa.ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("ladder_code", sa.Text(), sa.ForeignKey("ladders.code", ondelete="CASCADE"), nullable=False),
        sa.Column("is_win", sa.Boolean(), nullable=False),
        sa.Column("played_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_user_analytics_applied_user_ladder_played",
        "user_analytics_match_applied",
        ["user_id", "ladder_code", sa.text("played_at DESC")],
    )


def downgrade():
    op.drop_index("ix_user_analytics_applied_user_ladder_played", table_name="user_analytics_match_applied")
    op.drop_table("user_analytics_match_applied")

    op.drop_index("ix_user_analytics_ladder_rating", table_name="user_analytics_state")
    op.drop_index("ix_user_analytics_user", table_name="user_analytics_state")
    op.drop_table("user_analytics_state")
