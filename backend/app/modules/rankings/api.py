from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import sqlalchemy as sa

from app.db.session import get_db
from app.schemas.ranking import RankingOut, RankingRow

router = APIRouter()

@router.get("/{ladder_code}/{category_id}", response_model=RankingOut)
def ranking(
    ladder_code: str,
    category_id: str,
    country: str | None = Query(default=None, description="ISO-2 (ej: CO)"),
    city: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    country_norm = country.strip().upper() if country is not None else None
    city_norm = city.strip() if city is not None else None

    if country_norm == "":
        raise HTTPException(400, "country cannot be empty")
    if city_norm == "":
        raise HTTPException(400, "city cannot be empty")
    if country_norm is not None and len(country_norm) != 2:
        raise HTTPException(400, "country must be ISO-2 (e.g. CO)")
    if city_norm is not None and country_norm is None:
        raise HTTPException(400, "city filter requires country")

    where = [
        "s.ladder_code=:l",
        "s.category_id=:c",
        "p.is_public=true",
    ]
    params: dict[str, str] = {
        "l": ladder_code,
        "c": category_id,
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
        ladder_code=ladder_code,
        category_id=category_id,
        rows=[RankingRow(**r) for r in rows],
    )
