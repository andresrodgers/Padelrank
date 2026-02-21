from __future__ import annotations

import math
import os
import time

import pytest

from tests.testkit import confirm_match, create_match, create_user_with_profile


@pytest.mark.performance
def test_analytics_me_latency_smoke(api, identity_factory):
    if os.getenv("RUN_PERF_TESTS", "0") != "1":
        pytest.skip("Smoke de rendimiento deshabilitado. Usa RUN_PERF_TESTS=1.")

    users = [
        create_user_with_profile(
            api,
            identity_factory,
            alias_prefix=f"ana_perf_{i+1}",
            gender=gender,
            primary_category_code=cat,
            country="CO",
            city="Neiva",
            is_public=True,
        )
        for i, (gender, cat) in enumerate([("M", "6ta"), ("M", "6ta"), ("F", "D"), ("F", "D")])
    ]
    focus = users[0]

    for _ in range(8):
        m = create_match(api, focus["token"], u1=users[0], u2=users[1], u3=users[2], u4=users[3])
        confirm_match(api, users[1]["token"], m["id"])

    path = "/analytics/me?ladder=MX"
    for _ in range(3):
        api.call("GET", path, token=focus["token"])

    iterations = int(os.getenv("ANALYTICS_PERF_ITERATIONS", "25"))
    durations = []
    for _ in range(iterations):
        start = time.perf_counter()
        api.call("GET", path, token=focus["token"])
        durations.append(time.perf_counter() - start)

    durations.sort()
    p95_idx = max(0, math.ceil(len(durations) * 0.95) - 1)
    p95_ms = durations[p95_idx] * 1000.0
    avg_ms = (sum(durations) / len(durations)) * 1000.0

    p95_limit_ms = float(os.getenv("ANALYTICS_P95_THRESHOLD_MS", "500"))
    assert p95_ms <= p95_limit_ms, (
        f"Latencia alta en analytics/me. avg_ms={avg_ms:.1f}, "
        f"p95_ms={p95_ms:.1f}, threshold_ms={p95_limit_ms:.1f}"
    )
