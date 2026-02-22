from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class CheckoutSessionRequest:
    user_id: str
    plan_code: str
    success_url: str
    cancel_url: str


@dataclass(frozen=True)
class CheckoutSessionResponse:
    provider: str
    provider_checkout_id: str
    checkout_url: str
    expires_at: datetime | None = None


class BillingProviderAdapter(Protocol):
    provider_code: str

    def create_checkout_session(self, request: CheckoutSessionRequest) -> CheckoutSessionResponse:
        ...


class StripeBillingProvider:
    provider_code = "stripe"

    def create_checkout_session(self, request: CheckoutSessionRequest) -> CheckoutSessionResponse:
        raise NotImplementedError("Stripe aun no esta conectado en este entorno")


class NoopBillingProvider:
    provider_code = "none"

    def create_checkout_session(self, request: CheckoutSessionRequest) -> CheckoutSessionResponse:
        raise NotImplementedError("No hay proveedor de billing configurado")


def get_provider_adapter(provider_code: str) -> BillingProviderAdapter:
    code = (provider_code or "none").strip().lower()
    if code == "stripe":
        return StripeBillingProvider()
    return NoopBillingProvider()
