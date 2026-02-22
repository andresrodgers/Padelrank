import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AvatarPreset(Base):
    __tablename__ = "avatar_presets"

    key: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    display_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    image_url: Mapped[str] = mapped_column(sa.Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("true"))
    sort_order: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, server_default="100")
    created_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))

    __table_args__ = (
        sa.Index("ix_avatar_presets_active_order", "is_active", "sort_order"),
    )
