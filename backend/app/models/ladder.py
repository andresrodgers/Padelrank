import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class Ladder(Base):
    __tablename__ = "ladders"

    code: Mapped[str] = mapped_column(sa.Text, primary_key=True)  # HM/WM/MX
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("true"))
