from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
import hashlib
import hmac
import json
import time
from typing import Protocol
from urllib import parse as urlparse
from urllib import request as urlrequest

from jose import jwt

from app.core.config import settings


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


@dataclass(frozen=True)
class StoreValidationResponse:
    provider: str
    provider_customer_id: str | None
    provider_subscription_id: str
    product_id: str
    status: str
    cancel_at_period_end: bool
    current_period_start: datetime | None
    current_period_end: datetime | None
    raw_payload: dict


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


def _http_json_post(url: str, payload: dict, *, headers: dict[str, str] | None = None) -> dict:
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    body = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url=url, method="POST", data=body, headers=req_headers)
    with urlrequest.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def _http_form_post(url: str, payload: dict[str, str]) -> dict:
    body = urlparse.urlencode(payload).encode("utf-8")
    req = urlrequest.Request(
        url=url,
        method="POST",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urlrequest.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def _http_json_get(url: str, *, headers: dict[str, str]) -> dict:
    req = urlrequest.Request(url=url, method="GET", headers=headers)
    with urlrequest.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    txt = value.strip()
    if txt.endswith("Z"):
        txt = txt[:-1] + "+00:00"
    dt = datetime.fromisoformat(txt)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _epoch_ms_to_datetime(value: str | int | None) -> datetime | None:
    if value in (None, "", 0):
        return None
    try:
        ms = int(value)
    except Exception:
        return None
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def _parse_sig_header(signature_header: str | None) -> tuple[int, list[str]]:
    if not signature_header:
        return (0, [])
    timestamp = 0
    signatures: list[str] = []
    for part in signature_header.split(","):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        key = k.strip().lower()
        val = v.strip()
        if key == "t":
            try:
                timestamp = int(val)
            except Exception:
                timestamp = 0
        elif key in {"v1", "sig"}:
            signatures.append(val)
    return (timestamp, signatures)


def _verify_hmac_signature(raw_body: bytes, signature_header: str | None, secret: str, max_age_seconds: int) -> bool:
    timestamp, signatures = _parse_sig_header(signature_header)
    if timestamp <= 0 or not signatures:
        return False
    now = int(time.time())
    if abs(now - timestamp) > max_age_seconds:
        return False
    payload = f"{timestamp}.".encode("utf-8") + raw_body
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, s) for s in signatures)


def verify_provider_webhook_request(provider: str, headers, raw_body: bytes) -> bool:
    provider_code = (provider or "none").strip().lower()
    require_signature = bool(settings.BILLING_REQUIRE_WEBHOOK_SIGNATURE)
    max_age = int(settings.BILLING_WEBHOOK_MAX_AGE_SECONDS)

    if provider_code == "stripe":
        secret = settings.BILLING_WEBHOOK_STRIPE_SECRET or settings.BILLING_WEBHOOK_SECRET
        if not secret:
            return not require_signature
        sig = headers.get("stripe-signature")
        return _verify_hmac_signature(raw_body, sig, secret, max_age)

    provider_secrets = {
        "app_store": settings.BILLING_WEBHOOK_APP_STORE_SECRET,
        "google_play": settings.BILLING_WEBHOOK_GOOGLE_PLAY_SECRET,
        "manual": settings.BILLING_WEBHOOK_SECRET,
        "none": settings.BILLING_WEBHOOK_SECRET,
    }
    secret = provider_secrets.get(provider_code) or settings.BILLING_WEBHOOK_SECRET
    if not secret:
        return not require_signature
    sig = headers.get("x-billing-signature")
    return _verify_hmac_signature(raw_body, sig, secret, max_age)


def validate_app_store_receipt(receipt_data: str, *, environment: str = "auto") -> StoreValidationResponse:
    shared_secret = settings.APP_STORE_SHARED_SECRET
    if not shared_secret:
        raise NotImplementedError("Configura APP_STORE_SHARED_SECRET para validar recibos de App Store")

    env = (environment or "auto").strip().lower()
    if env not in {"auto", "production", "sandbox"}:
        raise ValueError("environment invalido (usa auto|production|sandbox)")

    payload = {
        "receipt-data": receipt_data,
        "password": shared_secret,
        "exclude-old-transactions": True,
    }

    if env == "sandbox":
        response = _http_json_post(settings.APP_STORE_VERIFY_URL_SANDBOX, payload)
    else:
        response = _http_json_post(settings.APP_STORE_VERIFY_URL_PROD, payload)
        if env == "auto" and int(response.get("status") or -1) == 21007:
            response = _http_json_post(settings.APP_STORE_VERIFY_URL_SANDBOX, payload)

    status_code = int(response.get("status") or -1)
    if status_code != 0:
        raise ValueError(f"App Store verifyReceipt rechazo el recibo (status={status_code})")

    latest_info = response.get("latest_receipt_info")
    if not isinstance(latest_info, list) or not latest_info:
        receipt_obj = response.get("receipt") if isinstance(response.get("receipt"), dict) else {}
        latest_info = receipt_obj.get("in_app", [])
    if not latest_info:
        raise ValueError("No se encontraron transacciones de suscripcion en el recibo")

    def _ms(item: dict, key: str) -> int:
        try:
            return int(item.get(key) or 0)
        except Exception:
            return 0

    latest = max(latest_info, key=lambda x: (_ms(x, "expires_date_ms"), _ms(x, "purchase_date_ms")))
    product_id = str(latest.get("product_id") or "").strip()
    if not product_id:
        raise ValueError("No se pudo resolver product_id en App Store")

    subscription_id = str(latest.get("original_transaction_id") or latest.get("transaction_id") or "").strip()
    if not subscription_id:
        raise ValueError("No se pudo resolver original_transaction_id en App Store")

    period_start = _epoch_ms_to_datetime(latest.get("purchase_date_ms"))
    period_end = _epoch_ms_to_datetime(latest.get("expires_date_ms"))
    cancellation = latest.get("cancellation_date")
    now = datetime.now(tz=timezone.utc)

    if cancellation:
        normalized_status = "canceled"
    elif period_end and period_end > now:
        normalized_status = "active"
    else:
        normalized_status = "canceled"

    provider_customer_id = str(
        latest.get("app_account_token")
        or latest.get("web_order_line_item_id")
        or ""
    ).strip() or None

    return StoreValidationResponse(
        provider="app_store",
        provider_customer_id=provider_customer_id,
        provider_subscription_id=subscription_id,
        product_id=product_id,
        status=normalized_status,
        cancel_at_period_end=(normalized_status == "canceled"),
        current_period_start=period_start,
        current_period_end=period_end,
        raw_payload={
            "source": "app_store_verify_receipt",
            "environment": env,
            "status": status_code,
            "latest_receipt": response.get("latest_receipt") or receipt_data,
            "latest_receipt_info": latest,
        },
    )


def _google_access_token() -> str:
    service_account_email = settings.GOOGLE_PLAY_SERVICE_ACCOUNT_EMAIL
    private_key = settings.GOOGLE_PLAY_SERVICE_ACCOUNT_PRIVATE_KEY_PEM
    if not service_account_email or not private_key:
        raise NotImplementedError(
            "Configura GOOGLE_PLAY_SERVICE_ACCOUNT_EMAIL y GOOGLE_PLAY_SERVICE_ACCOUNT_PRIVATE_KEY_PEM"
        )

    pem = private_key.replace("\\n", "\n")
    now = int(time.time())
    assertion = jwt.encode(
        {
            "iss": service_account_email,
            "scope": settings.GOOGLE_PLAY_ANDROID_PUBLISHER_SCOPE,
            "aud": settings.GOOGLE_PLAY_TOKEN_URI,
            "iat": now,
            "exp": now + 3600,
        },
        pem,
        algorithm="RS256",
    )
    token_payload = _http_form_post(
        settings.GOOGLE_PLAY_TOKEN_URI,
        {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        },
    )
    access_token = token_payload.get("access_token")
    if not access_token:
        raise ValueError("No se pudo obtener access_token para Google Play")
    return str(access_token)


def _google_state_to_status(state: str | None) -> str:
    mapping = {
        "SUBSCRIPTION_STATE_ACTIVE": "active",
        "SUBSCRIPTION_STATE_IN_GRACE_PERIOD": "past_due",
        "SUBSCRIPTION_STATE_ON_HOLD": "past_due",
        "SUBSCRIPTION_STATE_PAUSED": "past_due",
        "SUBSCRIPTION_STATE_PENDING": "incomplete",
        "SUBSCRIPTION_STATE_CANCELED": "canceled",
        "SUBSCRIPTION_STATE_EXPIRED": "canceled",
    }
    return mapping.get(str(state or "").strip().upper(), "incomplete")


def validate_google_play_purchase(*, purchase_token: str, package_name: str | None = None) -> StoreValidationResponse:
    pkg = package_name or settings.GOOGLE_PLAY_PACKAGE_NAME
    if not pkg:
        raise NotImplementedError("Configura GOOGLE_PLAY_PACKAGE_NAME para validar suscripciones Google Play")

    access_token = _google_access_token()
    url = (
        "https://androidpublisher.googleapis.com/androidpublisher/v3/"
        f"applications/{urlparse.quote(pkg, safe='')}/purchases/subscriptionsv2/tokens/{urlparse.quote(purchase_token, safe='')}"
    )
    response = _http_json_get(
        url,
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
    )

    line_items = response.get("lineItems") if isinstance(response.get("lineItems"), list) else []
    if not line_items:
        raise ValueError("Google Play no devolvio lineItems para la compra")

    def _expiry(item: dict) -> datetime | None:
        return _parse_iso_datetime(item.get("expiryTime"))

    latest_item = max(line_items, key=lambda x: (_expiry(x) or datetime(1970, 1, 1, tzinfo=timezone.utc)))
    product_id = str(latest_item.get("productId") or "").strip()
    if not product_id:
        raise ValueError("Google Play no devolvio productId")

    period_start = _parse_iso_datetime(latest_item.get("startTime"))
    period_end = _parse_iso_datetime(latest_item.get("expiryTime"))
    status = _google_state_to_status(response.get("subscriptionState"))
    provider_subscription_id = str(response.get("latestOrderId") or purchase_token).strip()
    external_ids = response.get("externalAccountIdentifiers") if isinstance(response.get("externalAccountIdentifiers"), dict) else {}
    provider_customer_id = str(
        external_ids.get("obfuscatedExternalAccountId")
        or external_ids.get("obfuscatedExternalProfileId")
        or ""
    ).strip() or None

    return StoreValidationResponse(
        provider="google_play",
        provider_customer_id=provider_customer_id,
        provider_subscription_id=provider_subscription_id,
        product_id=product_id,
        status=status,
        cancel_at_period_end=bool(response.get("canceledStateContext")) or status == "canceled",
        current_period_start=period_start,
        current_period_end=period_end,
        raw_payload={
            "source": "google_play_subscriptions_v2",
            "package_name": pkg,
            "purchase_token": purchase_token,
            "response": response,
        },
    )


def _decode_jws_unverified(token: str | None) -> dict:
    if not token:
        return {}
    try:
        claims = jwt.get_unverified_claims(token)
        return claims if isinstance(claims, dict) else {}
    except Exception:
        return {}


def _to_iso_from_ms(value: object | None) -> str | None:
    try:
        if value is None:
            return None
        ms = int(value)
        dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    except Exception:
        return None


def _google_notification_type_to_status(notification_type: int | None) -> str:
    # RTDN mapping simplificado hacia estados internos.
    mapping = {
        1: "active",    # RECOVERED
        2: "active",    # RENEWED
        3: "canceled",  # CANCELED
        4: "active",    # PURCHASED
        5: "past_due",  # ON_HOLD
        6: "active",    # IN_GRACE_PERIOD
        7: "canceled",  # RESTARTED/CANCELED legacy
        8: "canceled",  # PRICE_CHANGE_CONFIRMED legacy
        9: "active",    # DEFERRED
        10: "paused",   # PAUSED (se normaliza luego)
        11: "paused",   # PAUSE_SCHEDULE_CHANGED
        12: "revoked",  # REVOKED
        13: "expired",  # EXPIRED
    }
    raw = mapping.get(int(notification_type or 0), "incomplete")
    if raw in {"paused"}:
        return "past_due"
    if raw in {"revoked", "expired"}:
        return "canceled"
    return raw


def normalize_provider_webhook_payload(provider: str, payload: dict) -> dict:
    code = (provider or "").strip().lower()

    # Manual/Stripe/custom format already normalized.
    if isinstance(payload, dict) and payload.get("id") and payload.get("type"):
        return {
            "id": str(payload["id"]),
            "type": str(payload["type"]),
            "data": (payload.get("data") if isinstance(payload.get("data"), dict) else {}),
        }

    if code == "app_store":
        signed_payload = payload.get("signedPayload") if isinstance(payload, dict) else None
        claims = _decode_jws_unverified(signed_payload if isinstance(signed_payload, str) else None)
        notif_uuid = str(claims.get("notificationUUID") or payload.get("notificationUUID") or f"app_store_{int(time.time())}")
        notif_type = str(claims.get("notificationType") or "unknown")
        subtype = str(claims.get("subtype") or "")
        data_claim = claims.get("data") if isinstance(claims.get("data"), dict) else {}
        signed_tx = data_claim.get("signedTransactionInfo")
        tx_claims = _decode_jws_unverified(signed_tx if isinstance(signed_tx, str) else None)

        product_id = str(tx_claims.get("productId") or "")
        original_tx_id = str(tx_claims.get("originalTransactionId") or tx_claims.get("transactionId") or "")
        app_account_token = tx_claims.get("appAccountToken")
        expires_at = _to_iso_from_ms(tx_claims.get("expiresDate"))
        purchase_at = _to_iso_from_ms(tx_claims.get("purchaseDate"))

        status_map = {
            "SUBSCRIBED": "active",
            "DID_RENEW": "active",
            "DID_RECOVER": "active",
            "DID_FAIL_TO_RENEW": "past_due",
            "EXPIRED": "canceled",
            "REFUND": "canceled",
            "REVOKE": "canceled",
            "GRACE_PERIOD_EXPIRED": "canceled",
        }
        status = status_map.get(notif_type.upper(), "incomplete")

        data = {
            "user_id": app_account_token,
            "provider_customer_id": app_account_token,
            "provider_subscription_id": original_tx_id,
            "plan_code": None,  # se resolvera por product_id (mapa en backend)
            "product_id": product_id,
            "status": status,
            "cancel_at_period_end": status == "canceled",
            "current_period_start": purchase_at,
            "current_period_end": expires_at,
            "subtype": subtype,
        }
        return {
            "id": notif_uuid,
            "type": f"app_store.{notif_type.lower()}",
            "data": data,
        }

    if code == "google_play":
        msg = payload.get("message") if isinstance(payload.get("message"), dict) else {}
        message_id = str(msg.get("messageId") or payload.get("messageId") or f"google_play_{int(time.time())}")
        encoded = msg.get("data")
        decoded: dict = {}
        if isinstance(encoded, str) and encoded:
            try:
                raw = base64.b64decode(encoded).decode("utf-8")
                data_json = json.loads(raw)
                decoded = data_json if isinstance(data_json, dict) else {}
            except Exception:
                decoded = {}
        if not decoded and isinstance(payload.get("subscriptionNotification"), dict):
            decoded = payload

        sub_n = decoded.get("subscriptionNotification") if isinstance(decoded.get("subscriptionNotification"), dict) else {}
        purchase_token = str(sub_n.get("purchaseToken") or decoded.get("purchaseToken") or "")
        subscription_id = str(sub_n.get("subscriptionId") or decoded.get("subscriptionId") or "")
        notification_type = sub_n.get("notificationType") or decoded.get("notificationType")
        status = _google_notification_type_to_status(int(notification_type) if notification_type is not None else None)

        data = {
            "user_id": None,  # se resuelve por suscripcion existente
            "provider_customer_id": None,
            "provider_subscription_id": subscription_id or purchase_token,
            "purchase_token": purchase_token,
            "package_name": str(decoded.get("packageName") or ""),
            "product_id": subscription_id,
            "status": status,
            "cancel_at_period_end": status == "canceled",
            "current_period_start": None,
            "current_period_end": None,
        }
        return {
            "id": message_id,
            "type": "google_play.subscription_notification",
            "data": data,
        }

    raise ValueError("Formato de webhook no soportado para provider")
