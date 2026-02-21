from __future__ import annotations

import os
from uuid import uuid4

import pytest

from tests.testkit import ApiClient, IdentityFactory


@pytest.fixture(scope="session")
def api() -> ApiClient:
    if os.getenv("RUN_API_INTEGRATION", "0") != "1":
        pytest.skip("Tests de integracion deshabilitados. Usa RUN_API_INTEGRATION=1.")

    base_url = os.getenv("TEST_API_BASE_URL", "http://localhost:8000")
    client = ApiClient(base_url)
    try:
        health = client.call("GET", "/health")
    except Exception as exc:  # pragma: no cover - guard rail
        pytest.fail(f"API no disponible en {base_url}: {exc}")
    if not isinstance(health, dict) or not health.get("ok"):
        pytest.fail(f"Health check invalido en {base_url}: {health}")
    return client


@pytest.fixture(scope="session")
def identity_factory() -> IdentityFactory:
    return IdentityFactory(seed=uuid4().hex[:8])
