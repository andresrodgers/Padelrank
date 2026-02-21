from fastapi import APIRouter, Depends, HTTPException, Query
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.schemas.analytics import AnalyticsPublicOut, AnalyticsStateOut

router = APIRouter()

_VALID_LADDERS = {"HM", "WM", "MX"}


def _normalize_ladder(ladder: str | None) -> str | None:
    if ladder is None:
        return None
    out = ladder.strip().upper()
    if out not in _VALID_LADDERS:
        raise HTTPException(400, "ladder must be HM|WM|MX")
    return out


def _recent_form(bits: int, size: int, max_items: int = 10) -> list[str]:
    n = min(size, max_items)
    out: list[str] = []
    for i in range(n):
        out.append("W" if ((bits >> i) & 1) == 1 else "L")
    return out


def _query_states(db: Session, user_id: str, ladder: str | None):
    where = ["s.user_id=:u"]
    params: dict[str, object] = {"u": user_id}
    if ladder is not None:
        where.append("s.ladder_code=:ladder")
        params["ladder"] = ladder

    return db.execute(sa.text(f"""
        SELECT
            s.user_id::text as user_id,
            s.ladder_code,
            s.total_verified_matches,
            s.wins,
            s.losses,
            s.win_rate,
            s.current_streak_type,
            s.current_streak_len,
            s.best_win_streak,
            s.best_loss_streak,
            s.recent_form_bits,
            s.recent_form_size,
            s.recent_10_matches,
            s.recent_10_wins,
            s.recent_10_win_rate,
            s.current_rating,
            s.peak_rating,
            s.last_match_at,
            s.updated_at
        FROM user_analytics_state s
        WHERE {" AND ".join(where)}
        ORDER BY s.ladder_code
    """), params).mappings().all()


@router.get("/me", response_model=list[AnalyticsStateOut])
def analytics_me(
    ladder: str | None = Query(default=None, description="HM|WM|MX"),
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = _query_states(db, str(current.id), _normalize_ladder(ladder))
    out: list[AnalyticsStateOut] = []
    for r in rows:
        out.append(AnalyticsStateOut(
            **{
                **r,
                "recent_form": _recent_form(int(r["recent_form_bits"] or 0), int(r["recent_form_size"] or 0)),
                "win_rate": float(r["win_rate"] or 0.0),
                "recent_10_win_rate": float(r["recent_10_win_rate"] or 0.0),
            }
        ))
    return out


@router.get("/users/{user_id}", response_model=list[AnalyticsPublicOut])
def analytics_user_public(
    user_id: str,
    ladder: str | None = Query(default=None, description="HM|WM|MX"),
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    is_self = str(current.id) == user_id

    prof = db.execute(sa.text("""
        SELECT is_public
        FROM user_profiles
        WHERE user_id=:u
    """), {"u": user_id}).mappings().first()
    if not prof:
        raise HTTPException(404, "User not found")
    if (not is_self) and (not bool(prof["is_public"])):
        raise HTTPException(404, "Analytics not available")

    rows = _query_states(db, user_id, _normalize_ladder(ladder))
    out: list[AnalyticsPublicOut] = []
    for r in rows:
        out.append(AnalyticsPublicOut(
            **{
                **r,
                "win_rate": float(r["win_rate"] or 0.0),
                "recent_10_win_rate": float(r["recent_10_win_rate"] or 0.0),
            }
        ))
    return out
