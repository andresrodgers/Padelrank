import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()"))
    user_id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default="general")
    subject: Mapped[str] = mapped_column(sa.Text, nullable=False)
    message: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default="open")
    created_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))
    updated_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))

    __table_args__ = (
        sa.CheckConstraint(
            "category IN ('general','billing','premium','bug','abuse')",
            name="ck_support_tickets_category",
        ),
        sa.CheckConstraint(
            "status IN ('open','in_progress','closed','spam')",
            name="ck_support_tickets_status",
        ),
        sa.Index("ix_support_tickets_user_created", "user_id", sa.text("created_at DESC")),
        sa.Index("ix_support_tickets_status_created", "status", sa.text("created_at DESC")),
    )
