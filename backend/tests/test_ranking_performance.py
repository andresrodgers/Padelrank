from __future__ import annotations

import math
import os
import time

import pytest

from tests.testkit import create_user_with_profile, get_ladder_state


@pytest.mark.performance
def test_ranking_city_scope_latency_smoke(api, identity_factory):
    if os.getenv("RUN_PERF_TESTS", "0") != "1":
        pytest.skip("Smoke de rendimiento deshabilitado. Usa RUN_PERF_TESTS=1.")

    users = []
    for i in range(18):
        if i < 8:
            country, city = "CO", "Neiva"
        elif i < 14:
            country, city = "CO", "Bogota"
        else:
            country, city = "MX", "CDMX"
        users.append(
            create_user_with_profile(
                api,
                identity_factory,
                alias_prefix="perf_scope",
                gender="F",
                primary_category_code="D",
                country=country,
                city=city,
            )
        )

    category_id = get_ladder_state(api, users[0]["token"], "MX")["category_id"]
    ranking_path = f"/rankings/MX/{category_id}?country=CO&city=Neiva"

    for _ in range(3):
        api.call("GET", ranking_path)

    iterations = int(os.getenv("RANKING_PERF_ITERATIONS", "25"))
    durations = []
    for _ in range(iterations):
        start = time.perf_counter()
        api.call("GET", ranking_path)
        durations.append(time.perf_counter() - start)

    durations.sort()
    p95_idx = max(0, math.ceil(len(durations) * 0.95) - 1)
    p95_ms = durations[p95_idx] * 1000.0
    avg_ms = (sum(durations) / len(durations)) * 1000.0

    p95_limit_ms = float(os.getenv("RANKING_P95_THRESHOLD_MS", "700"))
    assert p95_ms <= p95_limit_ms, (
        f"Latencia alta en ranking city scope. avg_ms={avg_ms:.1f}, "
        f"p95_ms={p95_ms:.1f}, threshold_ms={p95_limit_ms:.1f}"
    )
