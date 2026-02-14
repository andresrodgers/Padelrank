import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    alias: Mapped[str] = mapped_column(sa.Text, unique=True, nullable=False)
    gender: Mapped[str] = mapped_column(sa.Text, nullable=False)  # 'M' or 'F'
    is_public: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("true"))
    created_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))
    updated_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))

    user = relationship("User", back_populates="profile")
