from __future__ import annotations

from urllib import error, request

import pytest

from tests.testkit import (
    ApiError,
    confirm_match,
    create_match,
    create_user_with_profile,
    get_ladder_state,
    register_user,
)


def test_play_eligibility_transition(api, identity_factory):
    token = register_user(api, identity_factory.next_phone())

    elig_before = api.call("GET", "/me/play-eligibility", token=token)
    assert elig_before["can_create_match"] is False

    api.call(
        "PATCH",
        "/me/profile",
        token=token,
        body={
            "alias": identity_factory.next_alias("elig"),
            "gender": "M",
            "primary_category_code": "6ta",
            "country": "CO",
            "city": "Neiva",
            "is_public": True,
        },
    )

    elig_after = api.call("GET", "/me/play-eligibility", token=token)
    assert elig_after["can_create_match"] is True
    assert elig_after["can_play"] is True


@pytest.mark.parametrize(
    "ladder_code, lineup",
    [
        ("MX", [("M", "6ta"), ("M", "6ta"), ("F", "D"), ("F", "D")]),
        ("HM", [("M", "6ta"), ("M", "6ta"), ("M", "6ta"), ("M", "6ta")]),
        ("WM", [("F", "D"), ("F", "D"), ("F", "D"), ("F", "D")]),
    ],
)
def test_match_confirmation_flow_by_ladder(api, identity_factory, ladder_code, lineup):
    users = [
        create_user_with_profile(
            api,
            identity_factory,
            alias_prefix=f"{ladder_code.lower()}p{i+1}",
            gender=gender,
            primary_category_code=cat,
            country="CO",
            city="Neiva",
        )
        for i, (gender, cat) in enumerate(lineup)
    ]

    match = create_match(api, users[0]["token"], u1=users[0], u2=users[1], u3=users[2], u4=users[3])
    assert match["status"] == "pending_confirm"
    assert match["confirmed_count"] == 1

    match_id = match["id"]
    confirmations = api.call("GET", f"/matches/{match_id}/confirmations", token=users[0]["token"])
    team_by_user = {row["user_id"]: row["team_no"] for row in confirmations["rows"]}
    creator_team = team_by_user[users[0]["id"]]

    other_team_user = next(u for u in users if team_by_user[u["id"]] != creator_team)
    confirm_match(api, other_team_user["token"], match_id)

    detail = api.call("GET", f"/matches/{match_id}/detail", token=users[0]["token"])
    assert detail["status"] == "verified"

    remaining = next(u for u in users if u["id"] not in {users[0]["id"], other_team_user["id"]})
    with pytest.raises(ApiError) as verified_err:
        confirm_match(api, remaining["token"], match_id)
    assert verified_err.value.status_code == 409

    outsider = create_user_with_profile(
        api,
        identity_factory,
        alias_prefix=f"out_{ladder_code.lower()}",
        gender="M" if ladder_code != "WM" else "F",
        primary_category_code="6ta" if ladder_code != "WM" else "D",
        country="CO",
        city="Medellin",
    )
    with pytest.raises(ApiError) as outsider_err:
        confirm_match(api, outsider["token"], match_id)
    assert outsider_err.value.status_code == 403

    for user in users:
        st = get_ladder_state(api, user["token"], ladder_code)
        assert st["verified_matches"] >= 1


def test_ranking_scope_filters(api, identity_factory):
    co_neiva = [
        create_user_with_profile(
            api,
            identity_factory,
            alias_prefix="scope_co_nva",
            gender="M",
            primary_category_code="1ra",
            country="QZ",
            city="Navo",
        )
        for _ in range(3)
    ]
    co_bogota = [
        create_user_with_profile(
            api,
            identity_factory,
            alias_prefix="scope_co_bog",
            gender="M",
            primary_category_code="1ra",
            country="QZ",
            city="Boga",
        )
        for _ in range(2)
    ]
    mx_cdmx = [
        create_user_with_profile(
            api,
            identity_factory,
            alias_prefix="scope_mx_cdmx",
            gender="M",
            primary_category_code="1ra",
            country="QX",
            city="Cido",
        )
        for _ in range(2)
    ]

    category_id = get_ladder_state(api, co_neiva[0]["token"], "HM")["category_id"]
    co_rows = api.call("GET", f"/rankings/HM/{category_id}?country=QZ")["rows"]
    neiva_rows = api.call("GET", f"/rankings/HM/{category_id}?country=QZ&city=navo")["rows"]

    co_ids = {row["user_id"] for row in co_rows}
    neiva_ids = {row["user_id"] for row in neiva_rows}

    expected_co_neiva = {u["id"] for u in co_neiva}
    expected_co_bogota = {u["id"] for u in co_bogota}
    expected_mx_cdmx = {u["id"] for u in mx_cdmx}

    assert expected_co_neiva.issubset(co_ids)
    assert expected_co_bogota.issubset(co_ids)
    assert expected_mx_cdmx.isdisjoint(co_ids)

    assert expected_co_neiva.issubset(neiva_ids)
    assert expected_co_bogota.isdisjoint(neiva_ids)
    assert expected_mx_cdmx.isdisjoint(neiva_ids)
    assert neiva_ids.issubset(co_ids)

    with pytest.raises(ApiError) as city_without_country:
        api.call("GET", f"/rankings/HM/{category_id}?city=Neiva")
    assert city_without_country.value.status_code == 400

    with pytest.raises(ApiError) as invalid_country:
        api.call("GET", f"/rankings/HM/{category_id}?country=COL")
    assert invalid_country.value.status_code == 400


def test_invalid_ids_return_400(api, identity_factory):
    focus = create_user_with_profile(
        api,
        identity_factory,
        alias_prefix="invalid_ids_focus",
        gender="M",
        primary_category_code="6ta",
        country="CO",
        city="Neiva",
    )

    with pytest.raises(ApiError) as invalid_ranking_category:
        api.call("GET", "/rankings/HM/not-a-uuid")
    assert invalid_ranking_category.value.status_code == 400

    with pytest.raises(ApiError) as invalid_match_id:
        api.call("GET", "/matches/not-a-uuid", token=focus["token"])
    assert invalid_match_id.value.status_code == 400

    with pytest.raises(ApiError) as invalid_analytics_user_id:
        api.call("GET", "/analytics/users/not-a-uuid", token=focus["token"])
    assert invalid_analytics_user_id.value.status_code == 400

    with pytest.raises(ApiError) as invalid_trend_interval:
        api.call("GET", "/analytics/me/dashboard?ladder=MX&trend_interval=year", token=focus["token"])
    assert invalid_trend_interval.value.status_code == 400


def test_health_security_headers_and_trusted_host(api):
    req = request.Request(url=f"{api.base_url}/health", method="GET")
    with request.urlopen(req, timeout=10) as resp:
        assert resp.status == 200
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert resp.headers.get("Permissions-Policy") == "camera=(), microphone=(), geolocation=()"
        assert resp.headers.get("Content-Security-Policy") == "frame-ancestors 'none'; base-uri 'self'"

    bad_host_req = request.Request(
        url=f"{api.base_url}/health",
        method="GET",
        headers={"Host": "invalid-host.local"},
    )
    with pytest.raises(error.HTTPError) as invalid_host:
        request.urlopen(bad_host_req, timeout=10)
    assert invalid_host.value.code == 400
