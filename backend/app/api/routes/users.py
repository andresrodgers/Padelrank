from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
import sqlalchemy as sa

from app.api.deps import get_current_user
from app.db.session import get_db
from app.schemas.users import UserLookupOut

router = APIRouter()

@router.get("/search", response_model=list[UserLookupOut])
def search_users(
    q: str = Query(..., min_length=1, max_length=50),
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    q2 = q.strip().lower()

    rows = db.execute(sa.text("""
        SELECT
            up.user_id::text as user_id,
            up.alias as alias
        FROM user_profiles up
        WHERE lower(up.alias) LIKE :pat
          AND up.is_public = true
        ORDER BY lower(up.alias)
        LIMIT 20
    """), {"pat": f"%{q2}%"}).mappings().all()

    return [UserLookupOut(**r) for r in rows]
