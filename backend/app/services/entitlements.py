from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.security import now_utc
from app.schemas.entitlements import (
    EntitlementContractOut,
    EntitlementFeatureSetOut,
    EntitlementOut,
    PlanCatalogOut,
    PlanDefinitionOut,
)

FREE_PLAN = "FREE"
PLUS_PLAN = "RIVIO_PLUS"
_VALID_PLANS = {FREE_PLAN, PLUS_PLAN}

_FREE_FEATURES = EntitlementFeatureSetOut(
    analytics_kpis=[
        "total_verified_matches",
        "wins_losses",
        "win_rate",
        "current_streak",
        "current_rating",
        "peak_rating",
        "recent_10_summary",
    ],
    analytics_series=[
        "rating_trend_last_20",
        "recent_win_rate_last_10",
    ],
    export_enabled=False,
    ads_enabled=True,
)

_PLUS_FEATURES = EntitlementFeatureSetOut(
    analytics_kpis=[
        "total_verified_matches",
        "wins_losses",
        "win_rate",
        "current_streak",
        "best_streaks",
        "current_rating",
        "peak_rating",
        "recent_10_summary",
        "rolling_win_rate_5_20_50",
        "activity_7_30_90",
        "close_matches_rate",
        "performance_vs_stronger_similar_weaker",
    ],
    analytics_series=[
        "rating_trend",
        "rolling_win_rate_timeline_10_20_50",
        "volume_week_month",
        "streak_timeline",
        "top_partners",
        "top_rivals",
    ],
    export_enabled=True,
    ads_enabled=False,
)


def _normalize_plan_code(raw: str | None) -> str:
    value = (raw or "").strip().upper()
    return value if value in _VALID_PLANS else FREE_PLAN


def ensure_entitlement_row(db: Session, user_id: str) -> dict[str, object]:
    row = db.execute(
        sa.text(
            """
            SELECT
                user_id::text AS user_id,
                plan_code,
                ads_enabled,
                activated_at,
                expires_at
            FROM user_entitlements
            WHERE user_id=:u
            """
        ),
        {"u": user_id},
    ).mappings().first()
    if row:
        return dict(row)

    db.execute(
        sa.text(
            """
            INSERT INTO user_entitlements (user_id, plan_code, ads_enabled)
            VALUES (:u, 'FREE', true)
            ON CONFLICT (user_id) DO NOTHING
            """
        ),
        {"u": user_id},
    )
    row = db.execute(
        sa.text(
            """
            SELECT
                user_id::text AS user_id,
                plan_code,
                ads_enabled,
                activated_at,
                expires_at
            FROM user_entitlements
            WHERE user_id=:u
            """
        ),
        {"u": user_id},
    ).mappings().first()
    if not row:
        # Guard rail in case of unexpected race/rollback.
        return {
            "user_id": user_id,
            "plan_code": FREE_PLAN,
            "ads_enabled": True,
            "activated_at": now_utc(),
            "expires_at": None,
        }
    return dict(row)


def resolve_effective_plan(row: dict[str, object]) -> str:
    plan_code = _normalize_plan_code(str(row.get("plan_code") or FREE_PLAN))
    expires_at = row.get("expires_at")
    if isinstance(expires_at, datetime) and now_utc() > expires_at:
        return FREE_PLAN
    return plan_code


def plan_features(plan_code: str) -> EntitlementFeatureSetOut:
    if plan_code == PLUS_PLAN:
        return _PLUS_FEATURES
    return _FREE_FEATURES


def entitlement_out(row: dict[str, object], effective_plan: str | None = None) -> EntitlementOut:
    plan_code = _normalize_plan_code(effective_plan or str(row.get("plan_code") or FREE_PLAN))
    ads_enabled = bool(row.get("ads_enabled", True))
    if plan_code == PLUS_PLAN:
        ads_enabled = False
    return EntitlementOut(
        plan_code=plan_code,
        ads_enabled=ads_enabled,
        activated_at=row.get("activated_at") or now_utc(),
        expires_at=row.get("expires_at"),
    )


def get_user_contract(db: Session, user_id: str) -> EntitlementContractOut:
    row = ensure_entitlement_row(db, user_id)
    effective_plan = resolve_effective_plan(row)
    current = entitlement_out(row, effective_plan=effective_plan)
    return EntitlementContractOut(
        current=current,
        basic=_FREE_FEATURES,
        plus=_PLUS_FEATURES,
        effective=plan_features(effective_plan),
    )


def get_plan_catalog(current_plan: str) -> PlanCatalogOut:
    return PlanCatalogOut(
        current_plan=_normalize_plan_code(current_plan),
        plans=[
            PlanDefinitionOut(
                plan_code=FREE_PLAN,
                display_name="Rivio",
                description="Plan base con estadisticas esenciales y anuncios.",
                features=_FREE_FEATURES,
            ),
            PlanDefinitionOut(
                plan_code=PLUS_PLAN,
                display_name="Rivio+",
                description="Plan premium con analitica avanzada, exportaciones y sin anuncios.",
                features=_PLUS_FEATURES,
            ),
        ],
    )
