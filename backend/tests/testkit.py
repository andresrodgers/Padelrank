from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib import error, request


class ApiError(RuntimeError):
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self.payload = payload
        super().__init__(f"HTTP {status_code}: {payload}")


class ApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def call(self, method: str, path: str, *, token: str | None = None, body=None, timeout: int = 20):
        url = f"{self.base_url}{path}"
        headers = {"Accept": "application/json"}
        payload = None
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if body is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(body).encode("utf-8")

        req = request.Request(url=url, data=payload, headers=headers, method=method.upper())
        try:
            with request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return _parse_payload(raw)
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            raise ApiError(exc.code, _parse_payload(raw)) from exc


@dataclass
class IdentityFactory:
    seed: str
    counter: int = 0
    _seed_digits: str = ""

    def __post_init__(self):
        # Stable 6-digit numeric chunk from seed to avoid reusing phones across test runs.
        seed_num = int(self.seed[:8], 16) % 1_000_000
        self._seed_digits = f"{seed_num:06d}"

    def next_phone(self) -> str:
        self.counter += 1
        # +57 + 10 digits
        return f"+57{self._seed_digits}{self.counter:04d}"

    def next_alias(self, prefix: str) -> str:
        self.counter += 1
        return f"{prefix}_{self.seed}_{self.counter}"


def _parse_payload(raw: str):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def register_user(api: ApiClient, phone: str, password: str | None = None) -> str:
    pwd = password or f"P@del_{phone[-4:]}_Aa1"
    req = api.call("POST", "/auth/otp/request", body={"phone_e164": phone, "purpose": "register"})
    code = req.get("dev_code") if isinstance(req, dict) else None
    if not code:
        raise AssertionError("No se recibio dev_code; verifica ENV=dev para tests de integracion.")

    try:
        tokens = api.call(
            "POST",
            "/auth/register/complete",
            body={
                "phone_e164": phone,
                "code": code,
                "password": pwd,
            },
        )
    except ApiError as exc:
        if exc.status_code != 409:
            raise
        tokens = api.call("POST", "/auth/login", body={"identifier": phone, "password": pwd})
    token = tokens.get("access_token") if isinstance(tokens, dict) else None
    if not token:
        raise AssertionError("No se recibio access_token.")
    return token


def create_user_with_profile(
    api: ApiClient,
    factory: IdentityFactory,
    *,
    alias_prefix: str,
    gender: str,
    primary_category_code: str,
    country: str = "CO",
    city: str | None = None,
    is_public: bool = True,
):
    phone = factory.next_phone()
    token = register_user(api, phone=phone)
    alias = factory.next_alias(alias_prefix)
    api.call(
        "PATCH",
        "/me/profile",
        token=token,
        body={
            "alias": alias,
            "gender": gender,
            "primary_category_code": primary_category_code,
            "country": country,
            "city": city,
            "is_public": is_public,
        },
    )
    me = api.call("GET", "/me", token=token)
    return {
        "id": me["id"],
        "token": token,
        "alias": alias,
        "phone": phone,
        "gender": gender,
        "country": country,
        "city": city,
    }


def get_ladder_state(api: ApiClient, token: str, ladder_code: str):
    rows = api.call("GET", "/me/ladder-states", token=token)
    for row in rows:
        if row["ladder_code"] == ladder_code:
            return row
    raise AssertionError(f"No existe ladder_state para {ladder_code}.")


def create_match(
    api: ApiClient,
    creator_token: str,
    *,
    u1: dict,
    u2: dict,
    u3: dict,
    u4: dict,
    club_id: str | None = None,
    played_at: str | None = None,
    score_json: dict | None = None,
):
    played_at_value = played_at or (datetime.now(timezone.utc) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    score_payload = score_json or {
        "sets": [
            {"t1": 6, "t2": 4},
            {"t1": 7, "t2": 5},
        ]
    }
    return api.call(
        "POST",
        "/matches",
        token=creator_token,
        body={
            "club_id": club_id,
            "played_at": played_at_value,
            "participants": [
                {"user_id": u1["id"], "team_no": 1},
                {"user_id": u3["id"], "team_no": 1},
                {"user_id": u2["id"], "team_no": 2},
                {"user_id": u4["id"], "team_no": 2},
            ],
            "score": {
                "score_json": score_payload
            },
        },
    )


def confirm_match(api: ApiClient, token: str, match_id: str):
    return api.call(
        "POST",
        f"/matches/{match_id}/confirm",
        token=token,
        body={"status": "confirmed", "source": "pytest"},
    )
