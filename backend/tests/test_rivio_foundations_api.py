from __future__ import annotations

import pytest

from tests.testkit import ApiError, create_user_with_profile


def _register_with_tokens(api, phone: str, password: str = "P@del_Test_Aa1"):
    req = api.call("POST", "/auth/otp/request", body={"phone_e164": phone, "purpose": "register"})
    code = req.get("dev_code")
    if not code:
        raise AssertionError("No se recibio dev_code para registrar usuario de prueba")
    return api.call(
        "POST",
        "/auth/register/complete",
        body={"phone_e164": phone, "code": code, "password": password},
    )


def test_entitlements_contract_and_catalog(api, identity_factory):
    user = create_user_with_profile(
        api,
        identity_factory,
        alias_prefix="ent_contract",
        gender="M",
        primary_category_code="6ta",
        country="CO",
        city="Neiva",
    )
    token = user["token"]

    contract = api.call("GET", "/entitlements/me", token=token)
    assert contract["current"]["plan_code"] == "FREE"
    assert contract["current"]["ads_enabled"] is True
    assert "total_verified_matches" in contract["effective"]["analytics_kpis"]
    assert contract["effective"]["export_enabled"] is False

    catalog = api.call("GET", "/entitlements/plans", token=token)
    codes = {row["plan_code"] for row in catalog["plans"]}
    assert {"FREE", "RIVIO_PLUS"}.issubset(codes)


def test_support_contact_and_tickets(api, identity_factory):
    user = create_user_with_profile(
        api,
        identity_factory,
        alias_prefix="support_user",
        gender="M",
        primary_category_code="6ta",
        country="CO",
        city="Neiva",
    )
    token = user["token"]

    contact = api.call("GET", "/support/contact", token=token)
    assert contact["to_email"]
    assert "mailto:" in contact["mailto_url"]
    assert user["id"] in contact["subject_template"]

    created = api.call(
        "POST",
        "/support/tickets",
        token=token,
        body={
            "category": "bug",
            "subject": "Error al cargar historial",
            "message": "Al abrir historial aparece un timeout en algunos casos.",
        },
    )
    assert created["status"] == "open"
    assert created["category"] == "bug"

    mine = api.call("GET", "/support/tickets/me?limit=10&offset=0", token=token)
    ids = {row["id"] for row in mine["rows"]}
    assert created["id"] in ids


def test_avatar_presets_and_selection(api, identity_factory):
    user = create_user_with_profile(
        api,
        identity_factory,
        alias_prefix="avatar_user",
        gender="F",
        primary_category_code="D",
        country="CO",
        city="Bogota",
    )
    token = user["token"]

    presets = api.call("GET", "/me/avatar-presets", token=token)
    assert len(presets) >= 1
    preset_key = presets[0]["key"]

    chosen = api.call("POST", "/me/avatar/preset", token=token, body={"preset_key": preset_key})
    assert chosen["mode"] == "preset"
    assert chosen["preset_key"] == preset_key
    assert chosen["resolved_image_url"]

    me = api.call("GET", "/me", token=token)
    assert me["profile"]["avatar_mode"] == "preset"
    assert me["profile"]["avatar_preset_key"] == preset_key
    assert me["profile"]["avatar_image_url"]

    policy = api.call("GET", "/me/avatar/upload-policy", token=token)
    assert policy["max_size_mb"] >= 1
    assert isinstance(policy["allowed_extensions"], list)


def test_logout_all_revokes_refresh_sessions(api, identity_factory):
    phone = identity_factory.next_phone()
    tokens = _register_with_tokens(api, phone=phone, password="P@del_Logout1")
    access = tokens["access_token"]
    refresh = tokens["refresh_token"]

    out = api.call("POST", "/auth/logout-all", token=access)
    assert out["ok"] is True

    with pytest.raises(ApiError) as refresh_err:
        api.call("POST", "/auth/refresh", body={"refresh_token": refresh})
    assert refresh_err.value.status_code == 401


def test_account_deletion_request_status_and_cancel(api, identity_factory):
    user = create_user_with_profile(
        api,
        identity_factory,
        alias_prefix="del_user",
        gender="M",
        primary_category_code="6ta",
        country="CO",
        city="Neiva",
    )
    token = user["token"]

    requested = api.call(
        "POST",
        "/me/account/deletion-request",
        token=token,
        body={"reason": "Prueba de flujo de eliminacion"},
    )
    assert requested["ok"] is True
    assert requested["deletion"]["status"] == "scheduled"

    with pytest.raises(ApiError) as blocked_me:
        api.call("GET", "/me", token=token)
    assert blocked_me.value.status_code == 403

    status = api.call("GET", "/me/account/deletion-status", token=token)
    assert status["status"] == "scheduled"

    cancelled = api.call("POST", "/me/account/deletion-cancel", token=token)
    assert cancelled["ok"] is True
    assert cancelled["deletion"]["status"] == "cancelled"

    me = api.call("GET", "/me", token=token)
    assert me["id"] == user["id"]
