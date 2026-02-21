import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class Match(Base):
    __tablename__ = "matches"

    id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()"))

    ladder_code: Mapped[str] = mapped_column(sa.Text, sa.ForeignKey("ladders.code", ondelete="RESTRICT"), nullable=False)
    category_id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, sa.ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False)
    club_id: Mapped[sa.Uuid | None] = mapped_column(sa.Uuid, sa.ForeignKey("clubs.id", ondelete="SET NULL"), nullable=True)

    played_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    created_by: Mapped[sa.Uuid] = mapped_column(sa.Uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    status: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default="pending_confirm")  # pending_confirm/verified/disputed/expired/void
    confirmation_deadline: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False)

    confirmed_count: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, server_default="0")
    has_dispute: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))

    rank_processed_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    anti_farming_weight: Mapped[float] = mapped_column(sa.Numeric(4, 2), nullable=False, server_default="1.00")

    created_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))
    updated_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))

    __table_args__ = (
        sa.Index("ix_matches_creator_status_deadline", "created_by", "status", "confirmation_deadline"),
        sa.Index("ix_matches_ladder_cat_status_played", "ladder_code", "category_id", "status", sa.text("played_at DESC")),
        sa.Index("ix_matches_status_played_created", "status", sa.text("played_at DESC"), sa.text("created_at DESC")),
        sa.Index("ix_matches_club_played", "club_id", sa.text("played_at DESC")),
        sa.CheckConstraint("status in ('pending_confirm','verified','disputed','expired','void')", name="ck_match_status"),
    )

class MatchParticipant(Base):
    __tablename__ = "match_participants"
    match_id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, sa.ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True)
    team_no: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    created_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))
    __table_args__ = (
        sa.CheckConstraint("team_no in (1,2)", name="ck_team_no"),
        sa.Index("ix_match_participants_match", "match_id"),
        sa.Index("ix_match_participants_user_match", "user_id", "match_id"),
    )

class MatchScore(Base):
    __tablename__ = "match_scores"
    match_id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, sa.ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True)
    score_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    winner_team_no: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    updated_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))
    __table_args__ = (
        sa.CheckConstraint("winner_team_no in (1,2)", name="ck_winner_team_no"),
    )

class MatchConfirmation(Base):
    __tablename__ = "match_confirmations"
    match_id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, sa.ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default="pending")  # pending/confirmed/disputed
    decided_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    source: Mapped[str | None] = mapped_column(sa.Text, nullable=True)  # app/whatsapp_link
    __table_args__ = (
        sa.CheckConstraint("status in ('pending','confirmed','disputed')", name="ck_confirmation_status"),
        sa.Index("ix_match_confirmations_user_status", "user_id", "status"),
        sa.Index("ix_match_confirmations_match_status", "match_id", "status"),
    )

class MatchDispute(Base):
    __tablename__ = "match_disputes"
    match_id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, sa.ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True)
    opened_by: Mapped[sa.Uuid] = mapped_column(sa.Uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    reason_code: Mapped[str] = mapped_column(sa.Text, nullable=False)
    comment: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    opened_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))
    status: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default="open")
    __table_args__ = (
        sa.CheckConstraint("status in ('open')", name="ck_dispute_status"),
    )
