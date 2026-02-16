from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import sqlalchemy as sa

from app.db.session import get_db
from app.schemas.config import ClubOut, LadderOut, CategoryOut

router = APIRouter()

@router.get("/clubs", response_model=list[ClubOut])
def list_clubs(db: Session = Depends(get_db)):
    rows = db.execute(sa.text("SELECT id::text as id, name, city, is_active FROM clubs WHERE is_active=true ORDER BY name")).mappings().all()
    return [ClubOut(**r) for r in rows]

@router.get("/ladders", response_model=list[LadderOut])
def list_ladders(db: Session = Depends(get_db)):
    rows = db.execute(sa.text("SELECT code, name, is_active FROM ladders WHERE is_active=true ORDER BY code")).mappings().all()
    return [LadderOut(**r) for r in rows]

@router.get("/categories", response_model=list[CategoryOut])
def list_categories(ladder: str, db: Session = Depends(get_db)):
    rows = db.execute(sa.text("""
        SELECT id::text as id, ladder_code, code, name, sort_order
        FROM categories
        WHERE ladder_code=:l
        ORDER BY sort_order, code
    """), {"l": ladder}).mappings().all()
    return [CategoryOut(**r) for r in rows]
