from fastapi import APIRouter, Depends, HTTPException, Query, Request
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.schemas.billing import (
    AppStoreValidateIn,
    BillingCheckoutCreateIn,
    BillingCheckoutCreateOut,
    BillingMeOut,
    BillingSimulateSubscriptionIn,
    BillingSimulateSubscriptionOut,
    BillingStoreValidationOut,
    BillingSubscriptionOut,
    BillingWebhookEventOut,
    GooglePlayValidateIn,
)
from app.services.billing import (
    current_provider_code,
    create_checkout_session_stub,
    ingest_webhook_event,
    reconcile_subscriptions,
    simulate_subscription,
    validate_and_sync_app_store_receipt,
    validate_and_sync_google_play_purchase,
)
from app.services.billing_provider import verify_provider_webhook_request
from app.services.audit import audit

router = APIRouter()

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
async def webhook_ingest(provider: str, request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    if not verify_provider_webhook_request(provider, request.headers, raw):
        raise HTTPException(401, "Firma de webhook invalida")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Payload JSON invalido")

    if not isinstance(payload, dict):
        raise HTTPException(400, "Payload JSON invalido")

    try:
        out = ingest_webhook_event(
            db,
            provider=provider,
            payload=payload,
        )
        db.commit()
        return BillingWebhookEventOut(**out)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))


@router.post("/store/app-store/validate", response_model=BillingStoreValidationOut)
def app_store_validate(payload: AppStoreValidateIn, current=Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        out = validate_and_sync_app_store_receipt(
            db,
            user_id=str(current.id),
            receipt_data=payload.receipt_data,
            environment=payload.environment,
        )
    except NotImplementedError as exc:
        raise HTTPException(503, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    audit(
        db,
        current.id,
        "billing_store_validation",
        out["provider_subscription_id"],
        "app_store_validated",
        {"product_id": out["product_id"], "status": out["status"]},
    )
    db.commit()
    return BillingStoreValidationOut(ok=True, **out)


@router.post("/store/google-play/validate", response_model=BillingStoreValidationOut)
def google_play_validate(payload: GooglePlayValidateIn, current=Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        out = validate_and_sync_google_play_purchase(
            db,
            user_id=str(current.id),
            purchase_token=payload.purchase_token,
            package_name=payload.package_name,
        )
    except NotImplementedError as exc:
        raise HTTPException(503, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    audit(
        db,
        current.id,
        "billing_store_validation",
        out["provider_subscription_id"],
        "google_play_validated",
        {"product_id": out["product_id"], "status": out["status"]},
    )
    db.commit()
    return BillingStoreValidationOut(ok=True, **out)


@router.post("/reconcile")
def run_reconciliation(
    limit: int = Query(default=200, ge=1, le=2000),
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if settings.ENV != "dev":
        raise HTTPException(404, "No disponible")
    result = reconcile_subscriptions(db, limit=limit)
    audit(
        db,
        current.id,
        "billing_reconcile",
        str(current.id),
        "manual_run",
        {"limit": limit, **result},
    )
    db.commit()
    return {"ok": True, **result}


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
