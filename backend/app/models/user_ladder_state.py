import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class UserLadderState(Base):
    __tablename__ = "user_ladder_state"

    user_id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    ladder_code: Mapped[str] = mapped_column(sa.Text, sa.ForeignKey("ladders.code", ondelete="CASCADE"), primary_key=True)
    category_id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, sa.ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False)

    rating: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="1000")
    verified_matches: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    is_provisional: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("true"))
    trust_score: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="100")

    created_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))
    updated_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))

    __table_args__ = (
        sa.Index("ix_user_ladder_rank", "ladder_code", "category_id", sa.text("rating DESC")),
        sa.Index("ix_user_ladder_rank_full", "ladder_code", "category_id", sa.text("rating DESC"), sa.text("verified_matches DESC")),
        sa.Index("ix_user_ladder_user", "user_id"),
    )
