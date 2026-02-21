import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    alias: Mapped[str] = mapped_column(sa.Text, unique=True, nullable=False)
    gender: Mapped[str] = mapped_column(sa.Text, nullable=False)  # 'M' or 'F'
    is_public: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("true"))
    country: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default="CO")
    city: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    handedness: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default="U")  # R/L/U
    preferred_side: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default="U")  # drive/reves/both/U
    birthdate: Mapped[sa.Date | None] = mapped_column(sa.Date, nullable=True)
    first_name: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    last_name: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))
    updated_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))

    __table_args__ = (
        sa.Index(
            "ix_user_profiles_country_public_user",
            "country",
            "user_id",
            postgresql_where=sa.text("is_public = true"),
        ),
        sa.Index(
            "ix_user_profiles_country_city_public_user",
            "country",
            sa.text("lower(city)"),
            "user_id",
            postgresql_where=sa.text("is_public = true AND city IS NOT NULL"),
        ),
    )

    user = relationship("User", back_populates="profile")
