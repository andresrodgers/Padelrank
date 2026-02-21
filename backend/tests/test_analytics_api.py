from __future__ import annotations

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


def test_analytics_incremental_and_idempotent_guard(api, identity_factory):
    users = _build_mx_users(api, identity_factory, "ana_inc")
    focus = users[0]

    m1 = create_match(api, focus["token"], u1=users[0], u2=users[1], u3=users[2], u4=users[3])
    confirm_match(api, users[1]["token"], m1["id"])

    me_rows = api.call("GET", "/analytics/me?ladder=MX", token=focus["token"])
    assert len(me_rows) == 1
    r1 = me_rows[0]
    assert r1["total_verified_matches"] == 1
    assert r1["wins"] == 1
    assert r1["losses"] == 0
    assert r1["current_streak_type"] == "W"
    assert r1["current_streak_len"] == 1
    assert r1["recent_10_matches"] == 1
    assert r1["recent_10_wins"] == 1
    assert r1["recent_form"][0] == "W"

    with pytest.raises(ApiError) as dup_confirm:
        confirm_match(api, users[2]["token"], m1["id"])
    assert dup_confirm.value.status_code == 409

    me_rows_after = api.call("GET", "/analytics/me?ladder=MX", token=focus["token"])
    assert me_rows_after[0]["total_verified_matches"] == 1


def test_analytics_recent_trend_and_public_visibility(api, identity_factory):
    users = _build_mx_users(api, identity_factory, "ana_vis")
    focus = users[0]
    viewer = create_user_with_profile(
        api,
        identity_factory,
        alias_prefix="ana_viewer",
        gender="M",
        primary_category_code="6ta",
        country="CO",
        city="Bogota",
        is_public=True,
    )

    # Match 1: focus win (team 1 wins by default).
    m1 = create_match(api, focus["token"], u1=users[0], u2=users[1], u3=users[2], u4=users[3])
    confirm_match(api, users[1]["token"], m1["id"])

    # Match 2: focus loss (team 2 wins).
    m2 = create_match(
        api,
        focus["token"],
        u1=users[0],
        u2=users[1],
        u3=users[2],
        u4=users[3],
        score_json={"sets": [{"t1": 4, "t2": 6}, {"t1": 5, "t2": 7}]},
    )
    confirm_match(api, users[1]["token"], m2["id"])

    # Match 3: focus win and close match (3 sets).
    m3 = create_match(
        api,
        focus["token"],
        u1=users[0],
        u2=users[1],
        u3=users[2],
        u4=users[3],
        score_json={"sets": [{"t1": 6, "t2": 3}, {"t1": 4, "t2": 6}, {"t1": 6, "t2": 2}]},
    )
    confirm_match(api, users[1]["token"], m3["id"])

    me = api.call("GET", "/analytics/me?ladder=MX", token=focus["token"])[0]
    assert me["total_verified_matches"] == 3
    assert me["wins"] == 2
    assert me["losses"] == 1
    assert me["current_streak_type"] == "W"
    assert me["current_streak_len"] == 1
    assert me["best_win_streak"] >= 1
    assert me["recent_10_matches"] == 3
    assert me["recent_10_wins"] == 2
    assert me["recent_form"][:3] == ["W", "L", "W"]
    assert me["rolling_5_win_rate"] == pytest.approx(66.67, abs=0.01)
    assert me["rolling_20_win_rate"] == pytest.approx(66.67, abs=0.01)
    assert me["rolling_50_win_rate"] == pytest.approx(66.67, abs=0.01)
    assert me["matches_7d"] == 3
    assert me["matches_30d"] == 3
    assert me["matches_90d"] == 3
    assert me["close_matches"] == 1
    assert me["close_match_rate"] == pytest.approx(33.33, abs=0.01)
    assert (
        me["vs_stronger_matches"] + me["vs_similar_matches"] + me["vs_weaker_matches"]
    ) == me["total_verified_matches"]

    public = api.call("GET", f"/analytics/users/{focus['id']}?ladder=MX", token=viewer["token"])
    assert len(public) == 1
    assert public[0]["total_verified_matches"] == 3
    assert "best_loss_streak" not in public[0]

    api.call("PATCH", "/me/profile", token=focus["token"], body={"is_public": False})
    with pytest.raises(ApiError) as hidden_err:
        api.call("GET", f"/analytics/users/{focus['id']}?ladder=MX", token=viewer["token"])
    assert hidden_err.value.status_code == 404

    # Self access must remain available even if UUID path uses uppercase.
    self_rows = api.call("GET", f"/analytics/users/{focus['id'].upper()}?ladder=MX", token=focus["token"])
    assert len(self_rows) == 1
    assert self_rows[0]["total_verified_matches"] == 3


def test_analytics_dashboard_series_and_top_stats(api, identity_factory):
    users = _build_mx_users(api, identity_factory, "ana_dash")
    focus = users[0]
    viewer = create_user_with_profile(
        api,
        identity_factory,
        alias_prefix="ana_dash_viewer",
        gender="M",
        primary_category_code="6ta",
        country="CO",
        city="Bogota",
        is_public=True,
    )

    m1 = create_match(api, focus["token"], u1=users[0], u2=users[1], u3=users[2], u4=users[3])
    confirm_match(api, users[1]["token"], m1["id"])

    m2 = create_match(
        api,
        focus["token"],
        u1=users[0],
        u2=users[1],
        u3=users[2],
        u4=users[3],
        score_json={"sets": [{"t1": 4, "t2": 6}, {"t1": 5, "t2": 7}]},
    )
    confirm_match(api, users[1]["token"], m2["id"])

    m3 = create_match(
        api,
        focus["token"],
        u1=users[0],
        u2=users[1],
        u3=users[2],
        u4=users[3],
        score_json={"sets": [{"t1": 6, "t2": 3}, {"t1": 4, "t2": 6}, {"t1": 6, "t2": 2}]},
    )
    confirm_match(api, users[1]["token"], m3["id"])

    dash_rows = api.call(
        "GET",
        "/analytics/me/dashboard?ladder=MX&trend_interval=match&points=20&top_n=5",
        token=focus["token"],
    )
    assert len(dash_rows) == 1
    dash = dash_rows[0]
    assert dash["state"]["total_verified_matches"] == 3
    assert len(dash["rating_trend"]) == 3
    assert len(dash["rolling_win_rate_trend"]) == 3
    assert len(dash["streak_timeline"]) == 3
    assert len(dash["volume_weekly"]) >= 1
    assert len(dash["volume_monthly"]) >= 1
    assert dash["top_partners"][0]["matches"] == 3
    assert len(dash["top_rivals"]) >= 2
    assert dash["top_rivals"][0]["matches"] == 3
    assert dash["top_rivals"][1]["matches"] == 3

    public_dash = api.call(
        "GET",
        f"/analytics/users/{focus['id']}/dashboard?ladder=MX&trend_interval=week&points=20&top_n=5",
        token=viewer["token"],
    )
    assert len(public_dash) == 1
    assert public_dash[0]["state"]["total_verified_matches"] == 3

    api.call("PATCH", "/me/profile", token=focus["token"], body={"is_public": False})
    with pytest.raises(ApiError) as hidden_err:
        api.call("GET", f"/analytics/users/{focus['id']}/dashboard?ladder=MX", token=viewer["token"])
    assert hidden_err.value.status_code == 404
