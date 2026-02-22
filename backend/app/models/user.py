import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()"))
    phone_e164: Mapped[str | None] = mapped_column(sa.Text, unique=True, nullable=True)
    email: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default="active")
    created_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))
    last_login_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        sa.CheckConstraint("status in ('active','blocked','pending_deletion','deleted')", name="ck_user_status"),
    )

    profile = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
