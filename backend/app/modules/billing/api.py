from fastapi import APIRouter, Depends, Header, HTTPException
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.schemas.billing import (
    BillingCheckoutCreateIn,
    BillingCheckoutCreateOut,
    BillingMeOut,
    BillingSimulateSubscriptionIn,
    BillingSimulateSubscriptionOut,
    BillingSubscriptionOut,
    BillingWebhookEventIn,
    BillingWebhookEventOut,
)
from app.services.billing import (
    current_provider_code,
    create_checkout_session_stub,
    ingest_webhook_event,
    simulate_subscription,
)

router = APIRouter()


def _is_webhook_signature_valid(signature: str | None) -> bool:
    secret = settings.BILLING_WEBHOOK_SECRET
    if not settings.BILLING_REQUIRE_WEBHOOK_SIGNATURE and not secret:
        return True
    if not secret:
        return False
    return bool(signature and signature == secret)


@router.get("/me", response_model=BillingMeOut)
def billing_me(current=Depends(get_current_user), db: Session = Depends(get_db)):
    provider = current_provider_code()
    customer = db.execute(
        sa.text(
            """
            SELECT provider_customer_id
            FROM billing_customers
            WHERE user_id=:u
            """
        ),
        {"u": str(current.id)},
    ).mappings().first()
    sub = db.execute(
        sa.text(
            """
            SELECT
                provider,
                provider_subscription_id,
                plan_code,
                status,
                cancel_at_period_end,
                current_period_start,
                current_period_end,
                started_at,
                canceled_at,
                updated_at
            FROM billing_subscriptions
            WHERE user_id=:u
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
        ),
        {"u": str(current.id)},
    ).mappings().first()
    ent = db.execute(
        sa.text(
            """
            SELECT plan_code
            FROM user_entitlements
            WHERE user_id=:u
            """
        ),
        {"u": str(current.id)},
    ).mappings().first()
    return BillingMeOut(
        provider=provider,  # type: ignore[arg-type]
        provider_customer_id=(customer["provider_customer_id"] if customer else None),
        entitlement_plan_code=((ent["plan_code"] if ent else "FREE")),
        checkout_supported=provider != "none",
        webhook_configured=bool(settings.BILLING_WEBHOOK_SECRET),
        subscription=(BillingSubscriptionOut(**sub) if sub else None),
    )


@router.post("/checkout-session", response_model=BillingCheckoutCreateOut)
def create_checkout_session(payload: BillingCheckoutCreateIn, current=Depends(get_current_user), db: Session = Depends(get_db)):
    success_url = payload.success_url or settings.BILLING_CHECKOUT_SUCCESS_URL
    cancel_url = payload.cancel_url or settings.BILLING_CHECKOUT_CANCEL_URL
    try:
        out = create_checkout_session_stub(
            db,
            user_id=str(current.id),
            plan_code=payload.plan_code,
            success_url=success_url,
            cancel_url=cancel_url,
        )
    except NotImplementedError as exc:
        raise HTTPException(501, str(exc))
    db.commit()
    return BillingCheckoutCreateOut(**out)


@router.post("/webhooks/{provider}", response_model=BillingWebhookEventOut)
def webhook_ingest(
    provider: str,
    payload: BillingWebhookEventIn,
    db: Session = Depends(get_db),
    x_billing_signature: str | None = Header(default=None),
):
    if not _is_webhook_signature_valid(x_billing_signature):
        raise HTTPException(401, "Firma de webhook invalida")

    try:
        out = ingest_webhook_event(
            db,
            provider=provider,
            payload=payload.model_dump(),
        )
        db.commit()
        return BillingWebhookEventOut(**out)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))


@router.post("/simulate/subscription", response_model=BillingSimulateSubscriptionOut)
def simulate_billing_subscription(
    payload: BillingSimulateSubscriptionIn,
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if settings.ENV != "dev":
        raise HTTPException(404, "No disponible")
    out = simulate_subscription(
        db,
        actor_user_id=str(current.id),
        provider=payload.provider,
        provider_customer_id=payload.provider_customer_id,
        provider_subscription_id=payload.provider_subscription_id,
        plan_code=payload.plan_code,
        status=payload.status,
        period_days=payload.period_days,
        cancel_at_period_end=payload.cancel_at_period_end,
    )
    db.commit()
    return BillingSimulateSubscriptionOut(
        ok=True,
        provider=payload.provider,
        provider_subscription_id=payload.provider_subscription_id,
        entitlement_plan_code=out["entitlement_plan_code"],  # type: ignore[arg-type]
    )
