import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class Category(Base):
    __tablename__ = "categories"

    id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()"))
    ladder_code: Mapped[str] = mapped_column(sa.Text, sa.ForeignKey("ladders.code", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(sa.Text, nullable=False)   # e.g. C1/C2/C3
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="1")

    __table_args__ = (
        sa.UniqueConstraint("ladder_code", "code", name="uq_category_ladder_code"),
    )
