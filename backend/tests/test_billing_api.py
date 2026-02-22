from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tests.testkit import create_user_with_profile


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
