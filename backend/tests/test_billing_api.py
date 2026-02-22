from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest

from tests.testkit import ApiError, confirm_match, create_match, create_user_with_profile


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def test_billing_me_defaults_and_checkout_stub(api, identity_factory):
    user = create_user_with_profile(
        api,
        identity_factory,
        alias_prefix="billing_defaults",
        gender="M",
        primary_category_code="6ta",
        country="CO",
        city="Neiva",
    )
    token = user["token"]

    me = api.call("GET", "/billing/me", token=token)
    assert me["provider"] == "none"
    assert me["entitlement_plan_code"] == "FREE"
    assert me["checkout_supported"] is False
    assert me["subscription"] is None

    checkout = api.call("POST", "/billing/checkout-session", token=token, body={"plan_code": "RIVIO_PLUS"})
    assert checkout["provider"] == "none"
    assert checkout["plan_code"] == "RIVIO_PLUS"
    assert checkout["is_stub"] is True
    assert checkout["status"] == "created"


def test_billing_simulate_updates_entitlements(api, identity_factory):
    user = create_user_with_profile(
        api,
        identity_factory,
        alias_prefix="billing_sim",
        gender="F",
        primary_category_code="D",
        country="CO",
        city="Bogota",
    )
    token = user["token"]
    sub_id = f"sub_sim_{identity_factory.seed}_{identity_factory.counter}"

    up = api.call(
        "POST",
        "/billing/simulate/subscription",
        token=token,
        body={
            "provider": "manual",
            "provider_subscription_id": sub_id,
            "plan_code": "RIVIO_PLUS",
            "status": "active",
            "period_days": 30,
        },
    )
    assert up["ok"] is True
    assert up["entitlement_plan_code"] == "RIVIO_PLUS"

    ent = api.call("GET", "/entitlements/me", token=token)
    assert ent["current"]["plan_code"] == "RIVIO_PLUS"
    assert ent["current"]["ads_enabled"] is False

    down = api.call(
        "POST",
        "/billing/simulate/subscription",
        token=token,
        body={
            "provider": "manual",
            "provider_subscription_id": sub_id,
            "plan_code": "RIVIO_PLUS",
            "status": "canceled",
            "period_days": 1,
            "cancel_at_period_end": True,
        },
    )
    assert down["ok"] is True
    assert down["entitlement_plan_code"] == "FREE"

    ent2 = api.call("GET", "/entitlements/me", token=token)
    assert ent2["current"]["plan_code"] == "FREE"
    assert ent2["current"]["ads_enabled"] is True


def test_billing_webhook_idempotent_processing(api, identity_factory):
    user = create_user_with_profile(
        api,
        identity_factory,
        alias_prefix="billing_hook",
        gender="M",
        primary_category_code="6ta",
        country="CO",
        city="Neiva",
    )
    token = user["token"]

    now = datetime.now(timezone.utc)
    evt_id = f"evt_{identity_factory.seed}_{identity_factory.counter}"
    payload = {
        "id": evt_id,
        "type": "subscription.updated",
        "data": {
            "user_id": user["id"],
            "provider_customer_id": f"cus_{identity_factory.seed}",
            "provider_subscription_id": f"sub_{identity_factory.seed}_{identity_factory.counter}",
            "plan_code": "RIVIO_PLUS",
            "status": "active",
            "current_period_start": _iso_utc(now),
            "current_period_end": _iso_utc(now + timedelta(days=30)),
        },
    }

    first = api.call("POST", "/billing/webhooks/manual", body=payload)
    assert first["duplicate"] is False
    assert first["processed"] is True
    assert first["status"] == "processed"

    ent = api.call("GET", "/entitlements/me", token=token)
    assert ent["current"]["plan_code"] == "RIVIO_PLUS"

    second = api.call("POST", "/billing/webhooks/manual", body=payload)
    assert second["duplicate"] is True


def test_store_validation_endpoints_require_provider_config(api, identity_factory):
    user = create_user_with_profile(
        api,
        identity_factory,
        alias_prefix="billing_store_cfg",
        gender="M",
        primary_category_code="6ta",
        country="CO",
        city="Neiva",
    )
    token = user["token"]

    with pytest.raises(ApiError) as app_store_err:
        api.call(
            "POST",
            "/billing/store/app-store/validate",
            token=token,
            body={"receipt_data": "A" * 24, "environment": "auto"},
        )
    assert app_store_err.value.status_code in (400, 503)

    with pytest.raises(ApiError) as google_err:
        api.call(
            "POST",
            "/billing/store/google-play/validate",
            token=token,
            body={"purchase_token": "tok_" + identity_factory.seed},
        )
    assert google_err.value.status_code in (400, 503)


def test_plus_export_analytics_flow(api, identity_factory):
    users = [
        create_user_with_profile(
            api,
            identity_factory,
            alias_prefix=f"billing_exp_{n}",
            gender=gender,
            primary_category_code=cat,
            country="CO",
            city="Neiva",
        )
        for n, (gender, cat) in enumerate([("M", "6ta"), ("M", "6ta"), ("F", "D"), ("F", "D")], start=1)
    ]
    focus = users[0]

    # Genera analitica para export.
    m1 = create_match(api, focus["token"], u1=users[0], u2=users[1], u3=users[2], u4=users[3])
    confirm_match(api, users[1]["token"], m1["id"])

    # FREE no exporta.
    with pytest.raises(ApiError) as free_export:
        api.call("GET", "/analytics/me/export?ladder=MX", token=focus["token"])
    assert free_export.value.status_code == 403

    # Sube a PLUS (modo dev) y exporta.
    api.call(
        "POST",
        "/billing/simulate/subscription",
        token=focus["token"],
        body={
            "provider": "manual",
            "provider_subscription_id": f"sub_export_{identity_factory.seed}",
            "plan_code": "RIVIO_PLUS",
            "status": "active",
            "period_days": 30,
        },
    )
    exported = api.call("GET", "/analytics/me/export?ladder=MX&points=20", token=focus["token"])
    assert exported["plan_code"] == "RIVIO_PLUS"
    assert exported["state"]["total_verified_matches"] >= 1


def test_google_play_rtdn_payload_is_accepted_as_webhook(api):
    rtdn = {
        "packageName": "com.rivio.app",
        "eventTimeMillis": "1730000000000",
        "subscriptionNotification": {
            "version": "1.0",
            "notificationType": 4,
            "purchaseToken": "tok_example_123",
            "subscriptionId": "rivio_plus_monthly",
        },
    }
    encoded = base64.b64encode(json.dumps(rtdn).encode("utf-8")).decode("utf-8")
    payload = {"message": {"messageId": "msg_rtdn_1", "data": encoded}}

    out = api.call("POST", "/billing/webhooks/google_play", body=payload)
    assert out["provider"] == "google_play"
    assert out["status"] in {"ignored", "processed", "error"}
