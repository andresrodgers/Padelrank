import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class RatingEvent(Base):
    __tablename__ = "rating_events"

    id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()"))
    match_id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, sa.ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)

    ladder_code: Mapped[str] = mapped_column(sa.Text, nullable=False)
    category_id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, nullable=False)
    user_id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    old_rating: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    new_rating: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    delta: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    k_factor: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    weight: Mapped[float] = mapped_column(sa.Numeric(4, 2), nullable=False, server_default="1.00")

    created_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))

    __table_args__ = (
        sa.Index("ix_rating_events_user_created", "user_id", sa.text("created_at DESC")),
        sa.Index("ix_rating_events_match", "match_id"),
    )
