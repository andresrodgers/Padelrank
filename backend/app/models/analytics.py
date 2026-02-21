import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserAnalyticsState(Base):
    __tablename__ = "user_analytics_state"

    user_id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    ladder_code: Mapped[str] = mapped_column(sa.Text, sa.ForeignKey("ladders.code", ondelete="CASCADE"), primary_key=True)

    total_verified_matches: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    wins: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    losses: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    win_rate: Mapped[float] = mapped_column(sa.Numeric(5, 2), nullable=False, server_default="0.00")

    current_streak_type: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    current_streak_len: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    best_win_streak: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    best_loss_streak: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")

    recent_form_bits: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, server_default="0")
    recent_form_size: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, server_default="0")
    recent_10_matches: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, server_default="0")
    recent_10_wins: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, server_default="0")
    recent_10_win_rate: Mapped[float] = mapped_column(sa.Numeric(5, 2), nullable=False, server_default="0.00")
    rolling_bits_50: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, server_default="0")
    rolling_size_50: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, server_default="0")
    rolling_5_win_rate: Mapped[float] = mapped_column(sa.Numeric(5, 2), nullable=False, server_default="0.00")
    rolling_20_win_rate: Mapped[float] = mapped_column(sa.Numeric(5, 2), nullable=False, server_default="0.00")
    rolling_50_win_rate: Mapped[float] = mapped_column(sa.Numeric(5, 2), nullable=False, server_default="0.00")
    matches_7d: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    matches_30d: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    matches_90d: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    close_matches: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    close_match_rate: Mapped[float] = mapped_column(sa.Numeric(5, 2), nullable=False, server_default="0.00")
    vs_stronger_matches: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    vs_stronger_wins: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    vs_stronger_win_rate: Mapped[float] = mapped_column(sa.Numeric(5, 2), nullable=False, server_default="0.00")
    vs_similar_matches: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    vs_similar_wins: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    vs_similar_win_rate: Mapped[float] = mapped_column(sa.Numeric(5, 2), nullable=False, server_default="0.00")
    vs_weaker_matches: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    vs_weaker_wins: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    vs_weaker_win_rate: Mapped[float] = mapped_column(sa.Numeric(5, 2), nullable=False, server_default="0.00")

    current_rating: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    peak_rating: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    last_match_id: Mapped[sa.Uuid | None] = mapped_column(sa.Uuid, sa.ForeignKey("matches.id", ondelete="SET NULL"), nullable=True)
    last_match_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    created_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))
    updated_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))

    __table_args__ = (
        sa.Index("ix_user_analytics_user", "user_id"),
        sa.Index("ix_user_analytics_ladder_rating", "ladder_code", sa.text("current_rating DESC")),
        sa.CheckConstraint("current_streak_type IN ('W','L') OR current_streak_type IS NULL", name="ck_user_analytics_streak_type"),
    )


class UserAnalyticsMatchApplied(Base):
    __tablename__ = "user_analytics_match_applied"

    user_id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    match_id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, sa.ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True)
    ladder_code: Mapped[str] = mapped_column(sa.Text, sa.ForeignKey("ladders.code", ondelete="CASCADE"), nullable=False)
    is_win: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    is_close_match: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    teammate_user_id: Mapped[sa.Uuid | None] = mapped_column(sa.Uuid, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    opponent_a_user_id: Mapped[sa.Uuid | None] = mapped_column(sa.Uuid, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    opponent_b_user_id: Mapped[sa.Uuid | None] = mapped_column(sa.Uuid, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    opponent_avg_rating: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    quality_bucket: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default="similar")
    rating_before: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    rating_after: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    rating_delta: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    rolling_10_win_rate: Mapped[float | None] = mapped_column(sa.Numeric(5, 2), nullable=True)
    rolling_20_win_rate: Mapped[float | None] = mapped_column(sa.Numeric(5, 2), nullable=True)
    rolling_50_win_rate: Mapped[float | None] = mapped_column(sa.Numeric(5, 2), nullable=True)
    streak_type_after: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    streak_len_after: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    played_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    created_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))

    __table_args__ = (
        sa.Index("ix_user_analytics_applied_user_ladder_played", "user_id", "ladder_code", sa.text("played_at DESC")),
        sa.Index("ix_user_analytics_applied_user_ladder_quality", "user_id", "ladder_code", "quality_bucket"),
        sa.Index("ix_user_analytics_applied_user_ladder_partner", "user_id", "ladder_code", "teammate_user_id"),
        sa.Index("ix_user_analytics_applied_user_ladder_rating", "user_id", "ladder_code", sa.text("played_at DESC"), "rating_after"),
        sa.CheckConstraint("quality_bucket IN ('stronger','similar','weaker')", name="ck_user_analytics_quality_bucket"),
        sa.CheckConstraint("streak_type_after IN ('W','L') OR streak_type_after IS NULL", name="ck_user_analytics_streak_after"),
    )


class UserAnalyticsPartnerStats(Base):
    __tablename__ = "user_analytics_partner_stats"

    user_id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    ladder_code: Mapped[str] = mapped_column(sa.Text, sa.ForeignKey("ladders.code", ondelete="CASCADE"), primary_key=True)
    partner_user_id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    matches: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    wins: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    losses: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    win_rate: Mapped[float] = mapped_column(sa.Numeric(5, 2), nullable=False, server_default="0.00")
    last_played_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    updated_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))

    __table_args__ = (
        sa.Index("ix_user_analytics_partner_top", "user_id", "ladder_code", sa.text("matches DESC"), sa.text("win_rate DESC")),
    )


class UserAnalyticsRivalStats(Base):
    __tablename__ = "user_analytics_rival_stats"

    user_id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    ladder_code: Mapped[str] = mapped_column(sa.Text, sa.ForeignKey("ladders.code", ondelete="CASCADE"), primary_key=True)
    rival_user_id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    matches: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    wins: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    losses: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    win_rate: Mapped[float] = mapped_column(sa.Numeric(5, 2), nullable=False, server_default="0.00")
    last_played_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    updated_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))

    __table_args__ = (
        sa.Index("ix_user_analytics_rival_top", "user_id", "ladder_code", sa.text("matches DESC"), sa.text("win_rate DESC")),
    )
