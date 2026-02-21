from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import sqlalchemy as sa
from uuid import UUID

from app.db.session import get_db
from app.schemas.ranking import RankingOut, RankingRow

router = APIRouter()
_VALID_LADDERS = {"HM", "WM", "MX"}


def _normalize_ladder(ladder_code: str) -> str:
    out = ladder_code.strip().upper()
    if out not in _VALID_LADDERS:
        raise HTTPException(400, "ladder_code debe ser HM|WM|MX")
    return out


def _normalize_category_id(category_id: str) -> str:
    try:
        return str(UUID(category_id))
    except Exception:
        raise HTTPException(400, "category_id debe ser un UUID valido")

@router.get("/{ladder_code}/{category_id}", response_model=RankingOut)
def ranking(
    ladder_code: str,
    category_id: str,
    country: str | None = Query(default=None, description="ISO-2 (ej: CO)"),
    city: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    ladder_norm = _normalize_ladder(ladder_code)
    category_id_norm = _normalize_category_id(category_id)
    country_norm = country.strip().upper() if country is not None else None
    city_norm = city.strip() if city is not None else None

    if country_norm == "":
        raise HTTPException(400, "country no puede estar vacio")
    if city_norm == "":
        raise HTTPException(400, "city no puede estar vacio")
    if country_norm is not None and len(country_norm) != 2:
        raise HTTPException(400, "country debe ser ISO-2 (ej. CO)")
    if city_norm is not None and country_norm is None:
        raise HTTPException(400, "el filtro city requiere country")

    where = [
        "s.ladder_code=:l",
        "s.category_id=:c",
        "p.is_public=true",
    ]
    params: dict[str, str] = {
        "l": ladder_norm,
        "c": category_id_norm,
    }
    if country_norm is not None:
        where.append("p.country=:country")
        params["country"] = country_norm
    if city_norm is not None:
        where.append("lower(p.city)=lower(:city)")
        params["city"] = city_norm

    rows = db.execute(sa.text(f"""
        SELECT s.user_id::text as user_id,
               p.alias as alias,
               s.rating as rating,
               s.verified_matches as verified_matches,
               s.is_provisional as is_provisional
        FROM user_ladder_state s
        JOIN user_profiles p ON p.user_id=s.user_id
        WHERE {" AND ".join(where)}
        ORDER BY s.rating DESC, s.verified_matches DESC
        LIMIT 200
    """), params).mappings().all()

    return RankingOut(
        ladder_code=ladder_norm,
        category_id=category_id_norm,
        rows=[RankingRow(**r) for r in rows],
    )
