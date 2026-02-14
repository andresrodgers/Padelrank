"""categories real + mx mapping

Revision ID: 0002_categories_real_and_mx_map
Revises: 0001_init_p0
Create Date: 2026-02-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_categories_real_and_mx_map"
down_revision = "0001_init_p0"
branch_labels = None
depends_on = None

def upgrade():
    # 1) limpiar categorías seed antiguas (C1-C3)
    op.execute("DELETE FROM categories;")

    # 2) insertar categorías reales
    op.execute("""
      INSERT INTO categories (ladder_code, code, name, sort_order) VALUES
      -- HM
      ('HM','1ra','1ra',1),
      ('HM','2da','2da',2),
      ('HM','3ra','3ra',3),
      ('HM','4ta','4ta',4),
      ('HM','5ta','5ta',5),
      ('HM','6ta','6ta',6),
      ('HM','7ma','7ma',7),

      -- WM
      ('WM','A','A',1),
      ('WM','B','B',2),
      ('WM','C','C',3),
      ('WM','D','D',4),

      -- MX
      ('MX','A','A',1),
      ('MX','B','B',2),
      ('MX','C','C',3),
      ('MX','D','D',4)
      ON CONFLICT (ladder_code, code) DO NOTHING;
    """)

    # 3) tabla de mapeo principal -> MX
    op.create_table(
        "mx_category_map",
        sa.Column("gender", sa.Text, nullable=False),          # 'M'/'F'
        sa.Column("primary_code", sa.Text, nullable=False),    # '1ra'..'7ma' o 'A'..'D'
        sa.Column("mx_code", sa.Text, nullable=False),         # 'A'..'D'
        sa.Column("mx_score", sa.SmallInteger, nullable=False),# A=1..D=4
        sa.PrimaryKeyConstraint("gender", "primary_code", name="pk_mx_category_map"),
        sa.CheckConstraint("gender in ('M','F')", name="ck_mxmap_gender"),
        sa.CheckConstraint("mx_code in ('A','B','C','D')", name="ck_mxmap_code"),
        sa.CheckConstraint("mx_score in (1,2,3,4)", name="ck_mxmap_score"),
    )

    op.execute("""
      INSERT INTO mx_category_map (gender, primary_code, mx_code, mx_score) VALUES
      -- Men -> MX
      ('M','1ra','A',1),
      ('M','2da','A',1),
      ('M','3ra','B',2),
      ('M','4ta','B',2),
      ('M','5ta','C',3),
      ('M','6ta','D',4),
      ('M','7ma','D',4),

      -- Women -> MX
      ('F','A','A',1),
      ('F','B','B',2),
      ('F','C','C',3),
      ('F','D','D',4);
    """)

def downgrade():
    op.drop_table("mx_category_map")
    op.execute("DELETE FROM categories;")
