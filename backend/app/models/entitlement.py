import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserEntitlement(Base):
    __tablename__ = "user_entitlements"

    user_id: Mapped[sa.Uuid] = mapped_column(
        sa.Uuid,
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    plan_code: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default="FREE")
    ads_enabled: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("true"))
    activated_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))
    expires_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))
    updated_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))

    __table_args__ = (
        sa.CheckConstraint("plan_code IN ('FREE','RIVIO_PLUS')", name="ck_user_entitlements_plan"),
        sa.Index("ix_user_entitlements_plan", "plan_code"),
    )
