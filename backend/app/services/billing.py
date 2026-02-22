from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import now_utc
from app.services.audit import audit
from app.services.billing_provider import (
    CheckoutSessionRequest,
    get_provider_adapter,
    normalize_provider_webhook_payload,
    validate_app_store_receipt,
    validate_google_play_purchase,
)

VALID_PROVIDERS = {"none", "stripe", "app_store", "google_play", "manual"}
VALID_SUBSCRIPTION_STATUS = {"trialing", "active", "past_due", "canceled", "incomplete", "incomplete_expired", "unpaid"}
VALID_PLAN_CODES = {"FREE", "RIVIO_PLUS"}
ENTITLES_PLUS_STATUSES = {"trialing", "active", "past_due"}


def current_provider_code() -> str:
    code = (settings.BILLING_PROVIDER or "none").strip().lower()
    return code if code in VALID_PROVIDERS else "none"


def _normalize_provider(provider: str | None) -> str:
    raw = (provider or "").strip().lower()
    if raw not in VALID_PROVIDERS:
        raise ValueError("provider invalido")
    return raw


def _normalize_plan_code(plan_code: str | None) -> str:
    raw = (plan_code or "FREE").strip().upper()
    if raw not in VALID_PLAN_CODES:
        raise ValueError("plan_code invalido")
    return raw


def _normalize_status(status: str | None) -> str:
    raw = (status or "incomplete").strip().lower()
    if raw not in VALID_SUBSCRIPTION_STATUS:
        raise ValueError("status de suscripcion invalido")
    return raw


def _parse_datetime(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        txt = value.strip()
        if txt.endswith("Z"):
            txt = txt[:-1] + "+00:00"
        dt = datetime.fromisoformat(txt)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    return None


def _try_uuid(value: object | None) -> str | None:
    if value is None:
        return None
    try:
        return str(UUID(str(value)))
    except Exception:
        return None


def _entitlement_from_subscription(plan_code: str, status: str, current_period_end: datetime | None) -> tuple[str, bool, datetime | None]:
    if plan_code == settings.BILLING_PLUS_PLAN_CODE and status in ENTITLES_PLUS_STATUSES:
        return ("RIVIO_PLUS", False, current_period_end)
    return ("FREE", True, None)


def _product_plan_map() -> dict[str, str]:
    out: dict[str, str] = {}
    raw = (settings.BILLING_PRODUCT_PLAN_MAP or "").strip()
    if not raw:
        return out
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    for item in parts:
        sep = "=" if "=" in item else ":"
        if sep not in item:
            continue
        product_id, plan_code = [x.strip() for x in item.split(sep, 1)]
        plan = _normalize_plan_code(plan_code)
        if product_id:
            out[product_id] = plan
    return out


def resolve_plan_code_from_product(product_id: str) -> str:
    mapping = _product_plan_map()
    plan = mapping.get(product_id)
    if not plan:
        raise ValueError(f"product_id '{product_id}' no mapeado. Configura BILLING_PRODUCT_PLAN_MAP")
    return plan


def _upsert_customer(
    db: Session,
    *,
    user_id: str,
    provider: str,
    provider_customer_id: str | None,
):
    db.execute(
        sa.text(
            """
            INSERT INTO billing_customers (user_id, provider, provider_customer_id)
            VALUES (:u, :provider, :customer_id)
            ON CONFLICT (user_id) DO UPDATE
            SET provider=:provider,
                provider_customer_id=:customer_id,
                updated_at=now()
            """
        ),
        {"u": user_id, "provider": provider, "customer_id": provider_customer_id},
    )


def _upsert_subscription(
    db: Session,
    *,
    user_id: str,
    provider: str,
    provider_subscription_id: str,
    plan_code: str,
    status: str,
    cancel_at_period_end: bool,
    current_period_start: datetime | None,
    current_period_end: datetime | None,
    payload: dict,
):
    db.execute(
        sa.text(
            """
            INSERT INTO billing_subscriptions (
                user_id,
                provider,
                provider_subscription_id,
                plan_code,
                status,
                cancel_at_period_end,
                current_period_start,
                current_period_end,
                started_at,
                canceled_at,
                raw_payload
            )
            VALUES (
                :u,
                :provider,
                :sub_id,
                :plan,
                :status,
                :cancel_at_period_end,
                :period_start,
                :period_end,
                now(),
                CASE WHEN :status='canceled' THEN now() ELSE NULL END,
                CAST(:payload AS jsonb)
            )
            ON CONFLICT (provider, provider_subscription_id) DO UPDATE
            SET user_id=:u,
                plan_code=:plan,
                status=:status,
                cancel_at_period_end=:cancel_at_period_end,
                current_period_start=:period_start,
                current_period_end=:period_end,
                canceled_at=CASE WHEN :status='canceled' THEN now() ELSE billing_subscriptions.canceled_at END,
                raw_payload=CAST(:payload AS jsonb),
                updated_at=now()
            """
        ),
        {
            "u": user_id,
            "provider": provider,
            "sub_id": provider_subscription_id,
            "plan": plan_code,
            "status": status,
            "cancel_at_period_end": cancel_at_period_end,
            "period_start": current_period_start,
            "period_end": current_period_end,
            "payload": json.dumps(payload or {}),
        },
    )


def _sync_entitlement_from_subscription(
    db: Session,
    *,
    user_id: str,
    plan_code: str,
    status: str,
    current_period_end: datetime | None,
):
    ent_plan, ads_enabled, expires_at = _entitlement_from_subscription(plan_code, status, current_period_end)
    db.execute(
        sa.text(
            """
            INSERT INTO user_entitlements (user_id, plan_code, ads_enabled, activated_at, expires_at)
            VALUES (:u, :plan, :ads, now(), :expires_at)
            ON CONFLICT (user_id) DO UPDATE
            SET plan_code=:plan,
                ads_enabled=:ads,
                activated_at=CASE
                    WHEN user_entitlements.plan_code <> :plan THEN now()
                    ELSE user_entitlements.activated_at
                END,
                expires_at=:expires_at,
                updated_at=now()
            """
        ),
        {"u": user_id, "plan": ent_plan, "ads": ads_enabled, "expires_at": expires_at},
    )
    return ent_plan


def create_checkout_session_stub(
    db: Session,
    *,
    user_id: str,
    plan_code: str,
    success_url: str,
    cancel_url: str,
):
    provider = current_provider_code()
    request = CheckoutSessionRequest(
        user_id=user_id,
        plan_code=plan_code,
        success_url=success_url,
        cancel_url=cancel_url,
    )

    if provider in {"none", "app_store", "google_play"}:
        expires_at = now_utc() + timedelta(minutes=30)
        is_store_managed = provider in {"app_store", "google_play"}
        detail = (
            "Compra administrada por tienda: usa validacion server-side de App Store/Google Play."
            if is_store_managed
            else "Billing provider no configurado. Checkout en modo stub."
        )
        row = db.execute(
            sa.text(
                """
                INSERT INTO billing_checkout_sessions (
                    user_id,
                    provider,
                    plan_code,
                    status,
                    provider_checkout_id,
                    checkout_url,
                    success_url,
                    cancel_url,
                    expires_at
                )
                VALUES (
                    :u,
                    :provider,
                    :plan,
                    'created',
                    :provider_checkout_id,
                    NULL,
                    :success_url,
                    :cancel_url,
                    :expires_at
                )
                RETURNING id::text AS id, status, expires_at
                """
            ),
            {
                "u": user_id,
                "provider": provider,
                "plan": plan_code,
                "provider_checkout_id": f"stub_{uuid4().hex}",
                "success_url": success_url,
                "cancel_url": cancel_url,
                "expires_at": expires_at,
            },
        ).mappings().one()
        return {
            "session_id": row["id"],
            "provider": provider,
            "plan_code": plan_code,
            "status": row["status"],
            "checkout_url": None,
            "is_stub": True,
            "detail": detail,
            "expires_at": row["expires_at"],
        }

    adapter = get_provider_adapter(provider)
    response = adapter.create_checkout_session(request)
    row = db.execute(
        sa.text(
            """
            INSERT INTO billing_checkout_sessions (
                user_id,
                provider,
                plan_code,
                status,
                provider_checkout_id,
                checkout_url,
                success_url,
                cancel_url,
                expires_at
            )
            VALUES (
                :u,
                :provider,
                :plan,
                'created',
                :provider_checkout_id,
                :checkout_url,
                :success_url,
                :cancel_url,
                :expires_at
            )
            RETURNING id::text AS id, status, expires_at
            """
        ),
        {
            "u": user_id,
            "provider": response.provider,
            "plan": plan_code,
            "provider_checkout_id": response.provider_checkout_id,
            "checkout_url": response.checkout_url,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "expires_at": response.expires_at,
        },
    ).mappings().one()
    return {
        "session_id": row["id"],
        "provider": response.provider,
        "plan_code": plan_code,
        "status": row["status"],
        "checkout_url": response.checkout_url,
        "is_stub": False,
        "detail": "Checkout creado",
        "expires_at": row["expires_at"],
    }


def apply_subscription_state(
    db: Session,
    *,
    user_id: str,
    provider: str,
    provider_customer_id: str | None,
    provider_subscription_id: str,
    plan_code: str,
    status: str,
    cancel_at_period_end: bool,
    current_period_start: datetime | None,
    current_period_end: datetime | None,
    payload: dict,
):
    provider_norm = _normalize_provider(provider)
    plan_norm = _normalize_plan_code(plan_code)
    status_norm = _normalize_status(status)

    _upsert_customer(
        db,
        user_id=user_id,
        provider=provider_norm,
        provider_customer_id=provider_customer_id,
    )
    _upsert_subscription(
        db,
        user_id=user_id,
        provider=provider_norm,
        provider_subscription_id=provider_subscription_id,
        plan_code=plan_norm,
        status=status_norm,
        cancel_at_period_end=cancel_at_period_end,
        current_period_start=current_period_start,
        current_period_end=current_period_end,
        payload=payload,
    )
    ent_plan = _sync_entitlement_from_subscription(
        db,
        user_id=user_id,
        plan_code=plan_norm,
        status=status_norm,
        current_period_end=current_period_end,
    )
    return {"entitlement_plan_code": ent_plan}


def _extract_user_subscription_data(payload: dict) -> dict[str, object]:
    data = payload.get("data") if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        data = {}
    user_id = _try_uuid(data.get("user_id"))
    provider_customer_id = data.get("provider_customer_id")
    provider_subscription_id = str(data.get("provider_subscription_id") or "")
    product_id = str(data.get("product_id") or "")
    plan_code = str(data.get("plan_code") or "FREE")
    status = str(data.get("status") or "incomplete")
    cancel_at_period_end = bool(data.get("cancel_at_period_end") or False)
    current_period_start = _parse_datetime(data.get("current_period_start"))
    current_period_end = _parse_datetime(data.get("current_period_end"))
    return {
        "user_id": user_id,
        "provider_customer_id": str(provider_customer_id) if provider_customer_id else None,
        "provider_subscription_id": provider_subscription_id,
        "product_id": product_id,
        "plan_code": plan_code,
        "status": status,
        "cancel_at_period_end": cancel_at_period_end,
        "current_period_start": current_period_start,
        "current_period_end": current_period_end,
    }


def _resolve_user_id_for_event(
    db: Session,
    *,
    provider: str,
    user_id: str | None,
    provider_subscription_id: str,
    purchase_token: str | None,
) -> str | None:
    if user_id:
        return user_id

    if provider_subscription_id:
        row = db.execute(
            sa.text(
                """
                SELECT user_id::text AS user_id
                FROM billing_subscriptions
                WHERE provider=:provider
                  AND provider_subscription_id=:sub_id
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """
            ),
            {"provider": provider, "sub_id": provider_subscription_id},
        ).mappings().first()
        if row:
            return str(row["user_id"])

    if purchase_token:
        row = db.execute(
            sa.text(
                """
                SELECT user_id::text AS user_id
                FROM billing_subscriptions
                WHERE provider=:provider
                  AND raw_payload->>'purchase_token'=:purchase_token
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """
            ),
            {"provider": provider, "purchase_token": purchase_token},
        ).mappings().first()
        if row:
            return str(row["user_id"])
    return None


def ingest_webhook_event(db: Session, *, provider: str, payload: dict):
    provider_norm = _normalize_provider(provider)
    normalized_payload = normalize_provider_webhook_payload(provider_norm, payload)
    event_id = str(normalized_payload.get("id") or "").strip()
    event_type = str(normalized_payload.get("type") or "").strip()
    if not event_id or not event_type:
        raise ValueError("Evento de webhook invalido")

    extracted = _extract_user_subscription_data(normalized_payload)
    user_id = _resolve_user_id_for_event(
        db,
        provider=provider_norm,
        user_id=(str(extracted["user_id"]) if extracted["user_id"] else None),
        provider_subscription_id=str(extracted["provider_subscription_id"]),
        purchase_token=(str(normalized_payload.get("data", {}).get("purchase_token")) if isinstance(normalized_payload.get("data"), dict) and normalized_payload.get("data", {}).get("purchase_token") else None),
    )

    inserted = db.execute(
        sa.text(
            """
            INSERT INTO billing_webhook_events (provider, event_id, event_type, user_id, payload, status)
            VALUES (:provider, :event_id, :event_type, :user_id, CAST(:payload AS jsonb), 'received')
            ON CONFLICT (provider, event_id) DO NOTHING
            RETURNING id::text AS id
            """
        ),
        {
            "provider": provider_norm,
            "event_id": event_id,
            "event_type": event_type,
            "user_id": user_id,
            "payload": json.dumps(normalized_payload),
        },
    ).mappings().first()
    if not inserted:
        row = db.execute(
            sa.text(
                """
                SELECT status
                FROM billing_webhook_events
                WHERE provider=:provider AND event_id=:event_id
                """
            ),
            {"provider": provider_norm, "event_id": event_id},
        ).mappings().first()
        return {
            "provider": provider_norm,
            "event_id": event_id,
            "duplicate": True,
            "processed": bool(row and row["status"] in ("processed", "ignored")),
            "status": (row["status"] if row else "ignored"),
        }

    event_row_id = inserted["id"]
    processed = False
    final_status = "ignored"
    error_message = None
    try:
        if not user_id or not extracted["provider_subscription_id"]:
            final_status = "ignored"
        elif event_type in {
            "subscription.created",
            "subscription.updated",
            "subscription.renewed",
            "invoice.paid",
        }:
            apply_subscription_state(
                db,
                user_id=user_id,
                provider=provider_norm,
                provider_customer_id=extracted["provider_customer_id"],  # type: ignore[arg-type]
                provider_subscription_id=str(extracted["provider_subscription_id"]),
                plan_code=(
                    resolve_plan_code_from_product(str(extracted["product_id"]))
                    if extracted["product_id"]
                    else str(extracted["plan_code"])
                ),
                status=str(extracted["status"]),
                cancel_at_period_end=bool(extracted["cancel_at_period_end"]),
                current_period_start=extracted["current_period_start"],  # type: ignore[arg-type]
                current_period_end=extracted["current_period_end"],  # type: ignore[arg-type]
                payload=normalized_payload,
            )
            processed = True
            final_status = "processed"
        elif event_type in {"subscription.deleted", "subscription.canceled", "invoice.payment_failed"}:
            apply_subscription_state(
                db,
                user_id=user_id,
                provider=provider_norm,
                provider_customer_id=extracted["provider_customer_id"],  # type: ignore[arg-type]
                provider_subscription_id=str(extracted["provider_subscription_id"]),
                plan_code=(
                    resolve_plan_code_from_product(str(extracted["product_id"]))
                    if extracted["product_id"]
                    else str(extracted["plan_code"] or "FREE")
                ),
                status="canceled",
                cancel_at_period_end=True,
                current_period_start=extracted["current_period_start"],  # type: ignore[arg-type]
                current_period_end=extracted["current_period_end"],  # type: ignore[arg-type]
                payload=normalized_payload,
            )
            processed = True
            final_status = "processed"
        else:
            final_status = "ignored"
    except Exception as exc:
        final_status = "error"
        error_message = str(exc)[:1000]

    db.execute(
        sa.text(
            """
            UPDATE billing_webhook_events
            SET status=:status, error_message=:error_message, processed_at=now()
            WHERE id=:id
            """
        ),
        {"id": event_row_id, "status": final_status, "error_message": error_message},
    )

    return {
        "provider": provider_norm,
        "event_id": event_id,
        "duplicate": False,
        "processed": processed,
        "status": final_status,
    }


def simulate_subscription(
    db: Session,
    *,
    actor_user_id: str,
    provider: str,
    provider_customer_id: str | None,
    provider_subscription_id: str,
    plan_code: str,
    status: str,
    period_days: int,
    cancel_at_period_end: bool,
):
    now = now_utc()
    result = apply_subscription_state(
        db,
        user_id=actor_user_id,
        provider=provider,
        provider_customer_id=provider_customer_id,
        provider_subscription_id=provider_subscription_id,
        plan_code=plan_code,
        status=status,
        cancel_at_period_end=cancel_at_period_end,
        current_period_start=now,
        current_period_end=now + timedelta(days=period_days),
        payload={"source": "simulate", "at": now.isoformat()},
    )
    audit(
        db,
        actor_user_id,
        "billing_subscription",
        provider_subscription_id,
        "simulated",
        {
            "provider": provider,
            "plan_code": plan_code,
            "status": status,
            "period_days": period_days,
            "cancel_at_period_end": cancel_at_period_end,
        },
    )
    return result


def _sync_store_validation(
    db: Session,
    *,
    user_id: str,
    provider: str,
    provider_customer_id: str | None,
    provider_subscription_id: str,
    product_id: str,
    status: str,
    cancel_at_period_end: bool,
    current_period_start: datetime | None,
    current_period_end: datetime | None,
    raw_payload: dict,
):
    plan_code = resolve_plan_code_from_product(product_id)
    applied = apply_subscription_state(
        db,
        user_id=user_id,
        provider=provider,
        provider_customer_id=provider_customer_id,
        provider_subscription_id=provider_subscription_id,
        plan_code=plan_code,
        status=status,
        cancel_at_period_end=cancel_at_period_end,
        current_period_start=current_period_start,
        current_period_end=current_period_end,
        payload=raw_payload,
    )
    return {
        "provider": provider,
        "provider_subscription_id": provider_subscription_id,
        "product_id": product_id,
        "status": status,
        "current_period_start": current_period_start,
        "current_period_end": current_period_end,
        "entitlement_plan_code": applied["entitlement_plan_code"],
    }


def validate_and_sync_app_store_receipt(
    db: Session,
    *,
    user_id: str,
    receipt_data: str,
    environment: str = "auto",
):
    result = validate_app_store_receipt(receipt_data, environment=environment)
    return _sync_store_validation(
        db,
        user_id=user_id,
        provider=result.provider,
        provider_customer_id=result.provider_customer_id,
        provider_subscription_id=result.provider_subscription_id,
        product_id=result.product_id,
        status=result.status,
        cancel_at_period_end=result.cancel_at_period_end,
        current_period_start=result.current_period_start,
        current_period_end=result.current_period_end,
        raw_payload=result.raw_payload,
    )


def validate_and_sync_google_play_purchase(
    db: Session,
    *,
    user_id: str,
    purchase_token: str,
    package_name: str | None = None,
):
    result = validate_google_play_purchase(purchase_token=purchase_token, package_name=package_name)
    return _sync_store_validation(
        db,
        user_id=user_id,
        provider=result.provider,
        provider_customer_id=result.provider_customer_id,
        provider_subscription_id=result.provider_subscription_id,
        product_id=result.product_id,
        status=result.status,
        cancel_at_period_end=result.cancel_at_period_end,
        current_period_start=result.current_period_start,
        current_period_end=result.current_period_end,
        raw_payload=result.raw_payload,
    )


def reconcile_subscriptions(db: Session, *, limit: int = 200):
    rows = db.execute(
        sa.text(
            """
            SELECT
                user_id::text AS user_id,
                provider,
                provider_subscription_id,
                raw_payload
            FROM billing_subscriptions
            WHERE provider IN ('app_store','google_play')
              AND status IN ('trialing','active','past_due')
            ORDER BY updated_at ASC, id ASC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).mappings().all()

    processed = 0
    updated = 0
    skipped = 0
    errors = 0
    for row in rows:
        processed += 1
        provider = str(row["provider"])
        payload = row["raw_payload"] if isinstance(row["raw_payload"], dict) else {}
        try:
            if provider == "app_store":
                receipt_data = payload.get("latest_receipt")
                if not receipt_data:
                    skipped += 1
                    continue
                out = validate_and_sync_app_store_receipt(
                    db,
                    user_id=str(row["user_id"]),
                    receipt_data=str(receipt_data),
                    environment="auto",
                )
                updated += 1 if out else 0
            elif provider == "google_play":
                purchase_token = payload.get("purchase_token")
                package_name = payload.get("package_name")
                if not purchase_token:
                    skipped += 1
                    continue
                out = validate_and_sync_google_play_purchase(
                    db,
                    user_id=str(row["user_id"]),
                    purchase_token=str(purchase_token),
                    package_name=(str(package_name) if package_name else None),
                )
                updated += 1 if out else 0
            else:
                skipped += 1
        except Exception:
            errors += 1

    return {
        "processed": processed,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
    }
