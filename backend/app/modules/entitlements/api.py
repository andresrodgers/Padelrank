from datetime import timedelta

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import now_utc
from app.db.session import get_db
from app.schemas.entitlements import EntitlementContractOut, EntitlementSimulateIn, PlanCatalogOut
from app.services.audit import audit
from app.services.entitlements import get_plan_catalog, get_user_contract

router = APIRouter()


@router.get("/me", response_model=EntitlementContractOut)
def my_entitlements(current=Depends(get_current_user), db: Session = Depends(get_db)):
    contract = get_user_contract(db, str(current.id))
    db.commit()
    return contract


@router.get("/plans", response_model=PlanCatalogOut)
def plan_catalog(current=Depends(get_current_user), db: Session = Depends(get_db)):
    contract = get_user_contract(db, str(current.id))
    db.commit()
    return get_plan_catalog(contract.current.plan_code)


@router.post("/me/simulate", response_model=EntitlementContractOut)
def simulate_plan(payload: EntitlementSimulateIn, current=Depends(get_current_user), db: Session = Depends(get_db)):
    if settings.ENV != "dev":
        raise HTTPException(404, "No disponible")

    expires_at = None
    if payload.duration_days:
        expires_at = now_utc() + timedelta(days=payload.duration_days)

    ads_enabled = payload.plan_code == "FREE"
    db.execute(
        sa.text(
            """
            INSERT INTO user_entitlements (user_id, plan_code, ads_enabled, activated_at, expires_at)
            VALUES (:u, :plan, :ads, now(), :expires_at)
            ON CONFLICT (user_id) DO UPDATE
            SET plan_code=:plan,
                ads_enabled=:ads,
                activated_at=now(),
                expires_at=:expires_at,
                updated_at=now()
            """
        ),
        {
            "u": str(current.id),
            "plan": payload.plan_code,
            "ads": ads_enabled,
            "expires_at": expires_at,
        },
    )
    audit(
        db,
        current.id,
        "entitlements",
        str(current.id),
        "plan_simulated",
        {"plan_code": payload.plan_code, "duration_days": payload.duration_days},
    )
    contract = get_user_contract(db, str(current.id))
    db.commit()
    return contract
