from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


BillingProvider = Literal["none", "stripe", "app_store", "google_play", "manual"]
BillingSubscriptionStatus = Literal["trialing", "active", "past_due", "canceled", "incomplete", "incomplete_expired", "unpaid"]


class BillingSubscriptionOut(BaseModel):
    provider: BillingProvider
    provider_subscription_id: str
    plan_code: Literal["FREE", "RIVIO_PLUS"]
    status: BillingSubscriptionStatus
    cancel_at_period_end: bool
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    started_at: datetime
    canceled_at: datetime | None = None
    updated_at: datetime


class BillingMeOut(BaseModel):
    provider: BillingProvider
    provider_customer_id: str | None = None
    entitlement_plan_code: Literal["FREE", "RIVIO_PLUS"]
    checkout_supported: bool
    webhook_configured: bool
    subscription: BillingSubscriptionOut | None = None


class BillingCheckoutCreateIn(BaseModel):
    plan_code: Literal["RIVIO_PLUS"] = "RIVIO_PLUS"
    success_url: str | None = Field(default=None, max_length=2048)
    cancel_url: str | None = Field(default=None, max_length=2048)


class BillingCheckoutCreateOut(BaseModel):
    session_id: str
    provider: BillingProvider
    plan_code: Literal["FREE", "RIVIO_PLUS"]
    status: Literal["created", "completed", "expired", "cancelled"]
    checkout_url: str | None = None
    is_stub: bool
    detail: str
    expires_at: datetime | None = None


class BillingWebhookEventIn(BaseModel):
    id: str = Field(..., min_length=3, max_length=255)
    type: str = Field(..., min_length=3, max_length=255)
    data: dict = Field(default_factory=dict)


class BillingWebhookEventOut(BaseModel):
    ok: bool = True
    provider: BillingProvider
    event_id: str
    duplicate: bool
    processed: bool
    status: Literal["processed", "ignored", "error"]


class BillingSimulateSubscriptionIn(BaseModel):
    provider: BillingProvider = "manual"
    provider_customer_id: str | None = Field(default=None, max_length=255)
    provider_subscription_id: str = Field(..., min_length=3, max_length=255)
    plan_code: Literal["FREE", "RIVIO_PLUS"] = "RIVIO_PLUS"
    status: BillingSubscriptionStatus = "active"
    period_days: int = Field(default=30, ge=1, le=3650)
    cancel_at_period_end: bool = False


class BillingSimulateSubscriptionOut(BaseModel):
    ok: bool = True
    provider: BillingProvider
    provider_subscription_id: str
    entitlement_plan_code: Literal["FREE", "RIVIO_PLUS"]


class AppStoreValidateIn(BaseModel):
    receipt_data: str = Field(..., min_length=20)
    environment: Literal["auto", "production", "sandbox"] = "auto"


class GooglePlayValidateIn(BaseModel):
    purchase_token: str = Field(..., min_length=8, max_length=4096)
    package_name: str | None = Field(default=None, min_length=3, max_length=255)


class BillingStoreValidationOut(BaseModel):
    ok: bool = True
    provider: BillingProvider
    provider_subscription_id: str
    product_id: str
    status: BillingSubscriptionStatus
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    entitlement_plan_code: Literal["FREE", "RIVIO_PLUS"]
