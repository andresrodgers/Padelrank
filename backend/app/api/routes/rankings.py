from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import sqlalchemy as sa

from app.db.session import get_db
from app.schemas.ranking import RankingOut, RankingRow

router = APIRouter()

@router.get("/{ladder_code}/{category_id}", response_model=RankingOut)
def ranking(ladder_code: str, category_id: str, db: Session = Depends(get_db)):
    rows = db.execute(sa.text("""
        SELECT s.user_id::text as user_id,
               p.alias as alias,
               s.rating as rating,
               s.verified_matches as verified_matches,
               s.is_provisional as is_provisional
        FROM user_ladder_state s
        JOIN user_profiles p ON p.user_id=s.user_id
        WHERE s.ladder_code=:l AND s.category_id=:c
          AND p.is_public=true
        ORDER BY s.rating DESC, s.verified_matches DESC
        LIMIT 200
    """), {"l": ladder_code, "c": category_id}).mappings().all()

    return RankingOut(
        ladder_code=ladder_code,
        category_id=category_id,
        rows=[RankingRow(**r) for r in rows],
    )
