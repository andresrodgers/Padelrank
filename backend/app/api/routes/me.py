from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import sqlalchemy as sa

from app.api.deps import get_current_user
from app.db.session import get_db
from app.schemas.me import MeOut, ProfileOut, ProfileUpdateIn, LadderStateOut
from app.services.audit import audit

from app.schemas.match import MyMatchesOut, MyMatchRowOut

router = APIRouter()

def _sum_verified_matches(db: Session, user_id) -> int:
    return int(db.execute(sa.text("""
        SELECT COALESCE(SUM(verified_matches), 0)
        FROM user_ladder_state
        WHERE user_id=:u
    """), {"u": user_id}).scalar_one())

def _get_category_id_by_code(db: Session, ladder_code: str, code: str) -> str:
    row = db.execute(sa.text("""
        SELECT id::text as id
        FROM categories
        WHERE ladder_code=:l AND code=:c
    """), {"l": ladder_code, "c": code}).mappings().first()
    if not row:
        raise HTTPException(400, f"Invalid category code '{code}' for ladder '{ladder_code}'")
    return row["id"]

def _get_mx_code_from_map(db: Session, gender: str, primary_code: str) -> str:
    row = db.execute(sa.text("""
        SELECT mx_code
        FROM mx_category_map
        WHERE gender=:g AND primary_code=:p
    """), {"g": gender, "p": primary_code}).mappings().first()
    if not row:
        raise HTTPException(400, "MX mapping missing for gender/category")
    return row["mx_code"]

def _upsert_ladder_state(db: Session, user_id, ladder_code: str, category_id: str):
    existing = db.execute(sa.text("""
        SELECT verified_matches, category_id::text AS category_id
        FROM user_ladder_state
        WHERE user_id=:u AND ladder_code=:l
    """), {"u": user_id, "l": ladder_code}).mappings().first()

    if existing:
        vm = int(existing["verified_matches"])
        current_cat = existing["category_id"]

        # Idempotencia: si mandan la misma categoría, OK sin tocar nada
        if current_cat == str(category_id):
            return

        # Si ya hay verificados, NO se permite cambiar
        if vm > 0:
            raise HTTPException(400, f"Cannot change category for ladder {ladder_code} after verified matches")

        # vm == 0: se permite corrección
        db.execute(sa.text("""
            UPDATE user_ladder_state
            SET category_id=:c, updated_at=now()
            WHERE user_id=:u AND ladder_code=:l
        """), {"u": user_id, "l": ladder_code, "c": category_id})
        return

    # No existe aún: crear
    db.execute(sa.text("""
        INSERT INTO user_ladder_state (user_id, ladder_code, category_id, rating, verified_matches, is_provisional, trust_score)
        VALUES (:u, :l, :c, 1000, 0, true, 100)
    """), {"u": user_id, "l": ladder_code, "c": category_id})

@router.get("", response_model=MeOut)
def me(current=Depends(get_current_user), db: Session = Depends(get_db)):
    prof = db.execute(sa.text("""
        SELECT alias, gender, is_public
        FROM user_profiles
        WHERE user_id=:u
    """), {"u": current.id}).mappings().first()

    profile = ProfileOut(**prof) if prof else None
    return MeOut(
        id=str(current.id),
        phone_e164=current.phone_e164,
        status=current.status,
        profile=profile,
    )

@router.get("/ladder-states", response_model=list[LadderStateOut])
def my_ladder_states(current=Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(sa.text("""
        SELECT s.ladder_code,
               s.category_id::text as category_id,
               c.code as category_code,
               c.name as category_name,
               s.rating,
               s.verified_matches,
               s.is_provisional,
               s.trust_score
        FROM user_ladder_state s
        JOIN categories c ON c.id = s.category_id
        WHERE s.user_id=:u
        ORDER BY s.ladder_code
    """), {"u": current.id}).mappings().all()
    return [LadderStateOut(**r) for r in rows]

@router.get("/matches", response_model=MyMatchesOut)
def my_matches(
    ladder: str | None = Query(default=None, description="HM|WM|MX"),
    status: str | None = Query(default=None, description="pending_confirm|verified|disputed|expired|void"),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = sa.text("""
        SELECT
            m.id::text as id,
            m.ladder_code,
            c.code as category_code,
            m.club_id::text as club_id,
            cl.name as club_name,
            m.played_at,
            m.status,
            m.confirmation_deadline,
            m.confirmed_count,
            m.has_dispute,
            mp.team_no as my_team_no,
            COALESCE(mc.status, 'pending') as my_confirmation_status
        FROM matches m
        JOIN match_participants mp
        ON mp.match_id = m.id AND mp.user_id = :u
        JOIN categories c
        ON c.id = m.category_id
        LEFT JOIN clubs cl
        ON cl.id = m.club_id
        LEFT JOIN match_confirmations mc
        ON mc.match_id = m.id AND mc.user_id = :u
        WHERE (:ladder IS NULL OR m.ladder_code = :ladder)
        AND (:status IS NULL OR m.status = :status)
        ORDER BY m.played_at DESC, m.created_at DESC
        LIMIT :limit OFFSET :offset
    """).bindparams(
        sa.bindparam("ladder", type_=sa.String()),
        sa.bindparam("status", type_=sa.String()),
    )

    rows = db.execute(stmt, {
        "u": str(current.id),
        "ladder": ladder,
        "status": status,
        "limit": limit,
        "offset": offset
    }).mappings().all()

    out_rows = [MyMatchRowOut(**r) for r in rows]
    next_offset = (offset + limit) if len(out_rows) == limit else None
    return MyMatchesOut(rows=out_rows, limit=limit, offset=offset, next_offset=next_offset)
