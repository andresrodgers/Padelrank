import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()"))
    actor_user_id: Mapped[sa.Uuid | None] = mapped_column(sa.Uuid, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    entity_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    action: Mapped[str] = mapped_column(sa.Text, nullable=False)
    data: Mapped[dict] = mapped_column(sa.JSON, nullable=False, server_default=sa.text("'{}'::json"))

    created_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))

    __table_args__ = (
        sa.Index("ix_audit_entity", "entity_type", "entity_id"),
        sa.Index("ix_audit_actor_created", "actor_user_id", sa.text("created_at DESC")),
    )
