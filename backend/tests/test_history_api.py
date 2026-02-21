from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tests.testkit import ApiError, confirm_match, create_match, create_user_with_profile


def _build_mx_users(api, identity_factory, prefix: str):
    return [
        create_user_with_profile(
            api,
            identity_factory,
            alias_prefix=f"{prefix}_{n}",
            gender=gender,
            primary_category_code=cat,
            country="CO",
            city="Neiva",
            is_public=True,
        )
        for n, (gender, cat) in enumerate([("M", "6ta"), ("M", "6ta"), ("F", "D"), ("F", "D")], start=1)
    ]


def test_history_me_verified_pending_filters(api, identity_factory):
    users = _build_mx_users(api, identity_factory, "hist_me")
    focus = users[0]

    verified_match = create_match(api, focus["token"], u1=users[0], u2=users[1], u3=users[2], u4=users[3])
    confirm_match(api, users[1]["token"], verified_match["id"])

    pending_match = create_match(api, focus["token"], u1=users[0], u2=users[1], u3=users[2], u4=users[3])

    default_rows = api.call("GET", "/history/me", token=focus["token"])["rows"]
    all_rows = api.call("GET", "/history/me?state_scope=all", token=focus["token"])["rows"]
    pending_rows = api.call("GET", "/history/me?state_scope=pending", token=focus["token"])["rows"]

    default_ids = {r["match_id"] for r in default_rows}
    all_ids = {r["match_id"] for r in all_rows}
    pending_ids = {r["match_id"] for r in pending_rows}

    assert verified_match["id"] in default_ids
    assert pending_match["id"] not in default_ids

    assert verified_match["id"] in all_ids
    assert pending_match["id"] in all_ids

    assert pending_ids == {pending_match["id"]}
    assert pending_rows[0]["status"] == "pending_confirm"
    assert pending_rows[0]["status_reason"] == "awaiting_confirmations"
    assert pending_rows[0]["ranking_impact"] is False
    assert pending_rows[0]["ranking_impact_reason"] == "not_verified"

    ladder_rows = api.call("GET", "/history/me?ladder=MX&state_scope=all", token=focus["token"])["rows"]
    assert {r["match_id"] for r in ladder_rows} == all_ids


def test_history_user_visibility_and_scope(api, identity_factory):
    users = _build_mx_users(api, identity_factory, "hist_pub")
    focus = users[0]
    viewer = create_user_with_profile(
        api,
        identity_factory,
        alias_prefix="hist_viewer",
        gender="M",
        primary_category_code="6ta",
        country="CO",
        city="Bogota",
        is_public=True,
    )

    verified_match = create_match(api, focus["token"], u1=users[0], u2=users[1], u3=users[2], u4=users[3])
    confirm_match(api, users[1]["token"], verified_match["id"])
    pending_match = create_match(api, focus["token"], u1=users[0], u2=users[1], u3=users[2], u4=users[3])

    pub_rows = api.call("GET", f"/history/users/{focus['id']}", token=viewer["token"])["rows"]
    pub_ids = {r["match_id"] for r in pub_rows}
    assert verified_match["id"] in pub_ids
    assert pending_match["id"] not in pub_ids
    assert all(r["visibility_reason"] == "public_verified_history" for r in pub_rows)

    with pytest.raises(ApiError) as scope_err:
        api.call("GET", f"/history/users/{focus['id']}?state_scope=all", token=viewer["token"])
    assert scope_err.value.status_code == 403

    api.call(
        "PATCH",
        "/me/profile",
        token=focus["token"],
        body={"is_public": False},
    )
    with pytest.raises(ApiError) as private_err:
        api.call("GET", f"/history/users/{focus['id']}", token=viewer["token"])
    assert private_err.value.status_code == 404


def test_history_detail_traceability_and_club_filters(api, identity_factory):
    users = _build_mx_users(api, identity_factory, "hist_detail")
    focus = users[0]
    outsider = create_user_with_profile(
        api,
        identity_factory,
        alias_prefix="hist_outsider",
        gender="F",
        primary_category_code="D",
        country="CO",
        city="Neiva",
        is_public=True,
    )

    clubs = api.call("GET", "/clubs")
    club = clubs[0]
    old_played_at = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

    verified_match = create_match(
        api,
        focus["token"],
        u1=users[0],
        u2=users[1],
        u3=users[2],
        u4=users[3],
        club_id=club["id"],
        played_at=old_played_at,
    )
    confirm_match(api, users[1]["token"], verified_match["id"])
    pending_match = create_match(api, focus["token"], u1=users[0], u2=users[1], u3=users[2], u4=users[3])

    # Filtros por fecha y club en timeline.
    date_from = (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()
    date_to = (datetime.now(timezone.utc) - timedelta(days=3)).date().isoformat()
    filtered = api.call(
        "GET",
        f"/history/me?state_scope=all&club_id={club['id']}&club_city={club['city']}&date_from={date_from}&date_to={date_to}",
        token=focus["token"],
    )["rows"]
    assert {r["match_id"] for r in filtered} == {verified_match["id"]}

    detail = api.call(
        "GET",
        f"/history/users/{focus['id']}/matches/{verified_match['id']}",
        token=outsider["token"],
    )
    assert detail["focus_user_id"] == focus["id"]
    assert detail["event"]["status"] == "verified"
    assert detail["event"]["ranking_impact_reason"] in {"verified_and_processed", "verified_pending_processing"}
    assert len(detail["participants"]) == 4
    assert len(detail["rival_aliases"]) == 2

    with pytest.raises(ApiError) as pending_hidden:
        api.call(
            "GET",
            f"/history/users/{focus['id']}/matches/{pending_match['id']}",
            token=outsider["token"],
        )
    assert pending_hidden.value.status_code == 404


def test_history_public_masks_private_participants(api, identity_factory):
    users = _build_mx_users(api, identity_factory, "hist_mask")
    focus = users[0]
    private_rival = users[1]
    viewer = create_user_with_profile(
        api,
        identity_factory,
        alias_prefix="hist_mask_viewer",
        gender="M",
        primary_category_code="6ta",
        country="CO",
        city="Bogota",
        is_public=True,
    )

    api.call("PATCH", "/me/profile", token=private_rival["token"], body={"is_public": False})

    verified_match = create_match(api, focus["token"], u1=users[0], u2=users[1], u3=users[2], u4=users[3])
    confirm_match(api, users[1]["token"], verified_match["id"])

    timeline_rows = api.call("GET", f"/history/users/{focus['id']}", token=viewer["token"])["rows"]
    match_row = next(r for r in timeline_rows if r["match_id"] == verified_match["id"])
    assert "[private]" in match_row["rival_aliases"]
    assert private_rival["alias"] not in match_row["rival_aliases"]

    detail = api.call(
        "GET",
        f"/history/users/{focus['id']}/matches/{verified_match['id']}",
        token=viewer["token"],
    )
    private_part = next(p for p in detail["participants"] if p["user_id"] == private_rival["id"])
    assert private_part["alias"] == "[private]"
    assert private_part["gender"] is None
