from __future__ import annotations

import pytest

from tests.testkit import (
    ApiError,
    confirm_match,
    create_match,
    create_user_with_profile,
    get_ladder_state,
)


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


@pytest.mark.regression
def test_regression_ranking_scopes(api, identity_factory):
    co_neiva = create_user_with_profile(
        api,
        identity_factory,
        alias_prefix="reg_rank_nva",
        gender="M",
        primary_category_code="1ra",
        country="QZ",
        city="Navo",
    )
    co_bogota = create_user_with_profile(
        api,
        identity_factory,
        alias_prefix="reg_rank_bog",
        gender="M",
        primary_category_code="1ra",
        country="QZ",
        city="Boga",
    )
    other_country = create_user_with_profile(
        api,
        identity_factory,
        alias_prefix="reg_rank_other",
        gender="M",
        primary_category_code="1ra",
        country="QX",
        city="Cido",
    )

    category_id = get_ladder_state(api, co_neiva["token"], "HM")["category_id"]
    country_rows = api.call("GET", f"/rankings/HM/{category_id}?country=QZ")["rows"]
    city_rows = api.call("GET", f"/rankings/HM/{category_id}?country=QZ&city=navo")["rows"]

    country_ids = {r["user_id"] for r in country_rows}
    city_ids = {r["user_id"] for r in city_rows}

    assert co_neiva["id"] in country_ids
    assert co_bogota["id"] in country_ids
    assert other_country["id"] not in country_ids

    assert co_neiva["id"] in city_ids
    assert co_bogota["id"] not in city_ids
    assert other_country["id"] not in city_ids

    with pytest.raises(ApiError) as city_without_country:
        api.call("GET", f"/rankings/HM/{category_id}?city=Navo")
    assert city_without_country.value.status_code == 400


@pytest.mark.regression
def test_regression_history_visibility(api, identity_factory):
    users = _build_mx_users(api, identity_factory, "reg_hist")
    focus = users[0]
    viewer = create_user_with_profile(
        api,
        identity_factory,
        alias_prefix="reg_hist_viewer",
        gender="M",
        primary_category_code="6ta",
        country="CO",
        city="Bogota",
        is_public=True,
    )

    verified_match = create_match(api, focus["token"], u1=users[0], u2=users[1], u3=users[2], u4=users[3])
    confirm_match(api, users[1]["token"], verified_match["id"])
    pending_match = create_match(api, focus["token"], u1=users[0], u2=users[1], u3=users[2], u4=users[3])

    me_default = api.call("GET", "/history/me", token=focus["token"])["rows"]
    me_all = api.call("GET", "/history/me?state_scope=all", token=focus["token"])["rows"]
    public_rows = api.call("GET", f"/history/users/{focus['id']}", token=viewer["token"])["rows"]

    me_default_ids = {r["match_id"] for r in me_default}
    me_all_ids = {r["match_id"] for r in me_all}
    public_ids = {r["match_id"] for r in public_rows}

    assert verified_match["id"] in me_default_ids
    assert pending_match["id"] not in me_default_ids
    assert {verified_match["id"], pending_match["id"]}.issubset(me_all_ids)
    assert verified_match["id"] in public_ids
    assert pending_match["id"] not in public_ids


@pytest.mark.regression
def test_regression_analytics_incremental_idempotent(api, identity_factory):
    users = _build_mx_users(api, identity_factory, "reg_ana")
    focus = users[0]

    match = create_match(api, focus["token"], u1=users[0], u2=users[1], u3=users[2], u4=users[3])
    confirm_match(api, users[1]["token"], match["id"])

    first = api.call("GET", "/analytics/me?ladder=MX", token=focus["token"])
    assert len(first) == 1
    assert first[0]["total_verified_matches"] == 1
    assert first[0]["wins"] == 1
    assert first[0]["losses"] == 0

    with pytest.raises(ApiError) as duplicate:
        confirm_match(api, users[2]["token"], match["id"])
    assert duplicate.value.status_code == 409

    after = api.call("GET", "/analytics/me?ladder=MX", token=focus["token"])
    assert after[0]["total_verified_matches"] == 1

    dashboard = api.call("GET", "/analytics/me/dashboard?ladder=MX&trend_interval=match&points=20", token=focus["token"])
    assert len(dashboard) == 1
    assert dashboard[0]["state"]["total_verified_matches"] == 1
    assert len(dashboard[0]["streak_timeline"]) == 1
