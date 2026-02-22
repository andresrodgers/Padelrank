"""billing scaffold provider-agnostic

Revision ID: 0020_billing_scaffold
Revises: 0019_user_status_lifecycle
Create Date: 2026-02-22
"""

from alembic import op
import sqlalchemy as sa


revision = "0020_billing_scaffold"
down_revision = "0019_user_status_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "billing_customers",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_customer_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "provider IN ('none','stripe','app_store','google_play','manual')",
            name="ck_billing_customers_provider",
        ),
        sa.UniqueConstraint("provider", "provider_customer_id", name="uq_billing_customers_provider_customer"),
    )
    op.create_index("ix_billing_customers_user_provider", "billing_customers", ["user_id", "provider"])

    op.create_table(
        "billing_subscriptions",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_subscription_id", sa.Text(), nullable=False),
        sa.Column("plan_code", sa.Text(), nullable=False, server_default="FREE"),
        sa.Column("status", sa.Text(), nullable=False, server_default="incomplete"),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "provider IN ('none','stripe','app_store','google_play','manual')",
            name="ck_billing_subscriptions_provider",
        ),
        sa.CheckConstraint("plan_code IN ('FREE','RIVIO_PLUS')", name="ck_billing_subscriptions_plan_code"),
        sa.CheckConstraint(
            "status IN ('trialing','active','past_due','canceled','incomplete','incomplete_expired','unpaid')",
            name="ck_billing_subscriptions_status",
        ),
        sa.UniqueConstraint("provider", "provider_subscription_id", name="uq_billing_subscriptions_provider_sub_id"),
    )
    op.create_index("ix_billing_subscriptions_user_status", "billing_subscriptions", ["user_id", "status"])
    op.create_index("ix_billing_subscriptions_period_end", "billing_subscriptions", [sa.text("current_period_end DESC")])

    op.create_table(
        "billing_webhook_events",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.Text(), nullable=False, server_default="received"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "provider IN ('none','stripe','app_store','google_play','manual')",
            name="ck_billing_webhook_events_provider",
        ),
        sa.CheckConstraint(
            "status IN ('received','processed','ignored','error')",
            name="ck_billing_webhook_events_status",
        ),
        sa.UniqueConstraint("provider", "event_id", name="uq_billing_webhook_events_provider_event_id"),
    )
    op.create_index(
        "ix_billing_webhook_events_status_received",
        "billing_webhook_events",
        ["status", sa.text("received_at DESC")],
    )

    op.create_table(
        "billing_checkout_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("plan_code", sa.Text(), nullable=False, server_default="RIVIO_PLUS"),
        sa.Column("status", sa.Text(), nullable=False, server_default="created"),
        sa.Column("provider_checkout_id", sa.Text(), nullable=True),
        sa.Column("checkout_url", sa.Text(), nullable=True),
        sa.Column("success_url", sa.Text(), nullable=True),
        sa.Column("cancel_url", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "provider IN ('none','stripe','app_store','google_play','manual')",
            name="ck_billing_checkout_sessions_provider",
        ),
        sa.CheckConstraint("plan_code IN ('FREE','RIVIO_PLUS')", name="ck_billing_checkout_sessions_plan_code"),
        sa.CheckConstraint(
            "status IN ('created','completed','expired','cancelled')",
            name="ck_billing_checkout_sessions_status",
        ),
        sa.UniqueConstraint("provider", "provider_checkout_id", name="uq_billing_checkout_sessions_provider_checkout_id"),
    )
    op.create_index(
        "ix_billing_checkout_sessions_user_created",
        "billing_checkout_sessions",
        ["user_id", sa.text("created_at DESC")],
    )


def downgrade():
    op.drop_index("ix_billing_checkout_sessions_user_created", table_name="billing_checkout_sessions")
    op.drop_table("billing_checkout_sessions")

    op.drop_index("ix_billing_webhook_events_status_received", table_name="billing_webhook_events")
    op.drop_table("billing_webhook_events")

    op.drop_index("ix_billing_subscriptions_period_end", table_name="billing_subscriptions")
    op.drop_index("ix_billing_subscriptions_user_status", table_name="billing_subscriptions")
    op.drop_table("billing_subscriptions")

    op.drop_index("ix_billing_customers_user_provider", table_name="billing_customers")
    op.drop_table("billing_customers")
