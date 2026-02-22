import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BillingCustomer(Base):
    __tablename__ = "billing_customers"

    id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()"))
    user_id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    provider: Mapped[str] = mapped_column(sa.Text, nullable=False)
    provider_customer_id: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))
    updated_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))

    __table_args__ = (
        sa.CheckConstraint(
            "provider IN ('none','stripe','app_store','google_play','manual')",
            name="ck_billing_customers_provider",
        ),
        sa.UniqueConstraint("provider", "provider_customer_id", name="uq_billing_customers_provider_customer"),
        sa.Index("ix_billing_customers_user_provider", "user_id", "provider"),
    )


class BillingSubscription(Base):
    __tablename__ = "billing_subscriptions"

    id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()"))
    user_id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(sa.Text, nullable=False)
    provider_subscription_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    plan_code: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default="FREE")
    status: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default="incomplete")
    cancel_at_period_end: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    current_period_start: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    started_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))
    canceled_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    raw_payload: Mapped[dict] = mapped_column(sa.JSON, nullable=False, server_default=sa.text("'{}'::jsonb"))
    created_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))
    updated_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))

    __table_args__ = (
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
        sa.Index("ix_billing_subscriptions_user_status", "user_id", "status"),
        sa.Index("ix_billing_subscriptions_period_end", sa.text("current_period_end DESC")),
    )


class BillingWebhookEvent(Base):
    __tablename__ = "billing_webhook_events"

    id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()"))
    provider: Mapped[str] = mapped_column(sa.Text, nullable=False)
    event_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    event_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    user_id: Mapped[sa.Uuid | None] = mapped_column(sa.Uuid, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    payload: Mapped[dict] = mapped_column(sa.JSON, nullable=False, server_default=sa.text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default="received")
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    received_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))
    processed_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        sa.CheckConstraint(
            "provider IN ('none','stripe','app_store','google_play','manual')",
            name="ck_billing_webhook_events_provider",
        ),
        sa.CheckConstraint(
            "status IN ('received','processed','ignored','error')",
            name="ck_billing_webhook_events_status",
        ),
        sa.UniqueConstraint("provider", "event_id", name="uq_billing_webhook_events_provider_event_id"),
        sa.Index("ix_billing_webhook_events_status_received", "status", sa.text("received_at DESC")),
    )


class BillingCheckoutSession(Base):
    __tablename__ = "billing_checkout_sessions"

    id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()"))
    user_id: Mapped[sa.Uuid] = mapped_column(sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(sa.Text, nullable=False)
    plan_code: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default="RIVIO_PLUS")
    status: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default="created")
    provider_checkout_id: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    checkout_url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    success_url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    cancel_url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    expires_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    completed_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))
    updated_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))

    __table_args__ = (
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
        sa.Index("ix_billing_checkout_sessions_user_created", "user_id", sa.text("created_at DESC")),
    )
