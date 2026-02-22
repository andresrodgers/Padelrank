import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AccountDeletionRequest(Base):
    __tablename__ = "account_deletion_requests"

    id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()"))
    user_id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    requested_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))
    scheduled_for: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    cancelled_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    executed_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default="self")

    __table_args__ = (
        sa.Index("ix_account_deletion_requests_user_requested", "user_id", sa.text("requested_at DESC")),
        sa.Index("ix_account_deletion_requests_scheduled", "scheduled_for"),
    )
