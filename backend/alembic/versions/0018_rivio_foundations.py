"""rivio foundations: entitlements, support, avatar, account deletion

Revision ID: 0018_rivio_foundations
Revises: 0017_analytics_kpis_and_series
Create Date: 2026-02-21
"""

from alembic import op
import sqlalchemy as sa


revision = "0018_rivio_foundations"
down_revision = "0017_analytics_kpis_and_series"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_entitlements",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("plan_code", sa.Text(), nullable=False, server_default="FREE"),
        sa.Column("ads_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("plan_code IN ('FREE','RIVIO_PLUS')", name="ck_user_entitlements_plan"),
    )
    op.create_index("ix_user_entitlements_plan", "user_entitlements", ["plan_code"])
    op.execute("""
        INSERT INTO user_entitlements (user_id, plan_code, ads_enabled)
        SELECT id, 'FREE', true
        FROM users
        ON CONFLICT (user_id) DO NOTHING
    """)

    op.create_table(
        "avatar_presets",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_avatar_presets_active_order", "avatar_presets", ["is_active", "sort_order"])
    op.execute("""
        INSERT INTO avatar_presets (key, display_name, image_url, sort_order, is_active) VALUES
        ('default_1', 'Rivio Azul', '/assets/avatars/default_1.png', 10, true),
        ('default_2', 'Rivio Coral', '/assets/avatars/default_2.png', 20, true),
        ('default_3', 'Rivio Arena', '/assets/avatars/default_3.png', 30, true),
        ('default_4', 'Rivio Bosque', '/assets/avatars/default_4.png', 40, true),
        ('default_5', 'Rivio Noche', '/assets/avatars/default_5.png', 50, true)
    """)

    op.add_column("user_profiles", sa.Column("avatar_mode", sa.Text(), nullable=False, server_default="preset"))
    op.add_column("user_profiles", sa.Column("avatar_preset_key", sa.Text(), nullable=True, server_default="default_1"))
    op.add_column("user_profiles", sa.Column("avatar_url", sa.Text(), nullable=True))
    op.execute("UPDATE user_profiles SET avatar_preset_key='default_1' WHERE avatar_preset_key IS NULL")
    op.create_foreign_key(
        "fk_user_profiles_avatar_preset_key",
        "user_profiles",
        "avatar_presets",
        ["avatar_preset_key"],
        ["key"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_user_profiles_avatar_mode",
        "user_profiles",
        "avatar_mode IN ('preset','upload')",
    )
    op.create_check_constraint(
        "ck_user_profiles_avatar_payload",
        "user_profiles",
        "(avatar_mode='preset' AND avatar_preset_key IS NOT NULL) OR (avatar_mode='upload' AND avatar_url IS NOT NULL)",
    )
    op.create_index("ix_user_profiles_avatar_mode", "user_profiles", ["avatar_mode"])

    op.create_table(
        "support_tickets",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.Text(), nullable=False, server_default="general"),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "category IN ('general','billing','premium','bug','abuse')",
            name="ck_support_tickets_category",
        ),
        sa.CheckConstraint(
            "status IN ('open','in_progress','closed','spam')",
            name="ck_support_tickets_status",
        ),
    )
    op.create_index(
        "ix_support_tickets_user_created",
        "support_tickets",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_support_tickets_status_created",
        "support_tickets",
        ["status", sa.text("created_at DESC")],
    )

    op.create_table(
        "account_deletion_requests",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=False, server_default="self"),
    )
    op.create_index(
        "ix_account_deletion_requests_user_requested",
        "account_deletion_requests",
        ["user_id", sa.text("requested_at DESC")],
    )
    op.create_index(
        "ix_account_deletion_requests_scheduled",
        "account_deletion_requests",
        ["scheduled_for"],
    )


def downgrade():
    op.drop_index("ix_account_deletion_requests_scheduled", table_name="account_deletion_requests")
    op.drop_index("ix_account_deletion_requests_user_requested", table_name="account_deletion_requests")
    op.drop_table("account_deletion_requests")

    op.drop_index("ix_support_tickets_status_created", table_name="support_tickets")
    op.drop_index("ix_support_tickets_user_created", table_name="support_tickets")
    op.drop_table("support_tickets")

    op.drop_index("ix_user_profiles_avatar_mode", table_name="user_profiles")
    op.drop_constraint("ck_user_profiles_avatar_payload", "user_profiles", type_="check")
    op.drop_constraint("ck_user_profiles_avatar_mode", "user_profiles", type_="check")
    op.drop_constraint("fk_user_profiles_avatar_preset_key", "user_profiles", type_="foreignkey")
    op.drop_column("user_profiles", "avatar_url")
    op.drop_column("user_profiles", "avatar_preset_key")
    op.drop_column("user_profiles", "avatar_mode")

    op.drop_index("ix_avatar_presets_active_order", table_name="avatar_presets")
    op.drop_table("avatar_presets")

    op.drop_index("ix_user_entitlements_plan", table_name="user_entitlements")
    op.drop_table("user_entitlements")
