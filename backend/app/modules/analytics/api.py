from fastapi import APIRouter, Depends, HTTPException, Query
import sqlalchemy as sa
from sqlalchemy.orm import Session
from uuid import UUID

from app.api.deps import get_current_user
from app.db.session import get_db
from app.schemas.analytics import (
    AnalyticsDashboardOut,
    AnalyticsPublicDashboardOut,
    AnalyticsPublicOut,
    AnalyticsStateOut,
    PartnerStatOut,
    RatingTrendPointOut,
    RivalStatOut,
    RollingWinRatePointOut,
    StreakPointOut,
    VolumePointOut,
)

router = APIRouter()

_VALID_LADDERS = {"HM", "WM", "MX"}
_VALID_TREND_INTERVALS = {"match", "week", "month"}


def _normalize_ladder(ladder: str | None) -> str | None:
    if ladder is None:
        return None
    out = ladder.strip().upper()
    if out not in _VALID_LADDERS:
        raise HTTPException(400, "ladder debe ser HM|WM|MX")
    return out


def _normalize_user_id(user_id: str) -> str:
    try:
        return str(UUID(user_id))
    except Exception:
        raise HTTPException(400, "user_id invalido")


def _normalize_trend_interval(interval: str | None) -> str:
    if interval is None:
        return "match"
    out = interval.strip().lower()
    if out not in _VALID_TREND_INTERVALS:
        raise HTTPException(400, "trend_interval debe ser match|week|month")
    return out


def _to_float(value: object | None) -> float:
    return float(value or 0.0)


def _recent_form(bits: int, size: int, max_items: int = 20) -> list[str]:
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
            s.rolling_5_win_rate,
            s.rolling_20_win_rate,
            s.rolling_50_win_rate,
            s.matches_7d,
            s.matches_30d,
            s.matches_90d,
            s.close_matches,
            s.close_match_rate,
            s.vs_stronger_matches,
            s.vs_stronger_wins,
            s.vs_stronger_win_rate,
            s.vs_similar_matches,
            s.vs_similar_wins,
            s.vs_similar_win_rate,
            s.vs_weaker_matches,
            s.vs_weaker_wins,
            s.vs_weaker_win_rate,
            s.current_rating,
            s.peak_rating,
            s.last_match_at,
            s.updated_at
        FROM user_analytics_state s
        WHERE {" AND ".join(where)}
        ORDER BY s.ladder_code
    """), params).mappings().all()


def _state_common_kwargs(r: dict[str, object]) -> dict[str, object]:
    return {
        "user_id": r["user_id"],
        "ladder_code": r["ladder_code"],
        "total_verified_matches": int(r["total_verified_matches"] or 0),
        "wins": int(r["wins"] or 0),
        "losses": int(r["losses"] or 0),
        "win_rate": _to_float(r["win_rate"]),
        "current_streak_type": r["current_streak_type"],
        "current_streak_len": int(r["current_streak_len"] or 0),
        "best_win_streak": int(r["best_win_streak"] or 0),
        "recent_10_matches": int(r["recent_10_matches"] or 0),
        "recent_10_wins": int(r["recent_10_wins"] or 0),
        "recent_10_win_rate": _to_float(r["recent_10_win_rate"]),
        "rolling_5_win_rate": _to_float(r["rolling_5_win_rate"]),
        "rolling_20_win_rate": _to_float(r["rolling_20_win_rate"]),
        "rolling_50_win_rate": _to_float(r["rolling_50_win_rate"]),
        "matches_7d": int(r["matches_7d"] or 0),
        "matches_30d": int(r["matches_30d"] or 0),
        "matches_90d": int(r["matches_90d"] or 0),
        "close_matches": int(r["close_matches"] or 0),
        "close_match_rate": _to_float(r["close_match_rate"]),
        "vs_stronger_matches": int(r["vs_stronger_matches"] or 0),
        "vs_stronger_wins": int(r["vs_stronger_wins"] or 0),
        "vs_stronger_win_rate": _to_float(r["vs_stronger_win_rate"]),
        "vs_similar_matches": int(r["vs_similar_matches"] or 0),
        "vs_similar_wins": int(r["vs_similar_wins"] or 0),
        "vs_similar_win_rate": _to_float(r["vs_similar_win_rate"]),
        "vs_weaker_matches": int(r["vs_weaker_matches"] or 0),
        "vs_weaker_wins": int(r["vs_weaker_wins"] or 0),
        "vs_weaker_win_rate": _to_float(r["vs_weaker_win_rate"]),
        "current_rating": int(r["current_rating"]) if r["current_rating"] is not None else None,
        "last_match_at": r["last_match_at"],
    }


def _private_state_out(r: dict[str, object]) -> AnalyticsStateOut:
    payload = _state_common_kwargs(r)
    payload["best_loss_streak"] = int(r["best_loss_streak"] or 0)
    payload["recent_form"] = _recent_form(int(r["recent_form_bits"] or 0), int(r["recent_form_size"] or 0))
    payload["peak_rating"] = int(r["peak_rating"]) if r["peak_rating"] is not None else None
    payload["updated_at"] = r["updated_at"]
    return AnalyticsStateOut(**payload)


def _public_state_out(r: dict[str, object]) -> AnalyticsPublicOut:
    payload = _state_common_kwargs(r)
    return AnalyticsPublicOut(**payload)


def _trend_bucket_expr(interval: str) -> str:
    if interval == "week":
        return "date_trunc('week', played_at)"
    if interval == "month":
        return "date_trunc('month', played_at)"
    raise ValueError("interval debe ser week|month")


def _query_rating_trend(
    db: Session,
    *,
    user_id: str,
    ladder_code: str,
    trend_interval: str,
    points: int,
) -> list[RatingTrendPointOut]:
    params = {"u": user_id, "l": ladder_code, "limit": points}
    if trend_interval == "match":
        rows = db.execute(sa.text("""
            SELECT
                t.match_id::text AS match_id,
                t.played_at AS at,
                t.rating_after AS rating
            FROM (
                SELECT match_id, played_at, rating_after
                FROM user_analytics_match_applied
                WHERE user_id=:u
                  AND ladder_code=:l
                  AND rating_after IS NOT NULL
                ORDER BY played_at DESC, match_id DESC
                LIMIT :limit
            ) t
            ORDER BY t.played_at ASC, t.match_id ASC
        """), params).mappings().all()
        return [
            RatingTrendPointOut(
                at=r["at"],
                rating=int(r["rating"]) if r["rating"] is not None else None,
                match_id=r["match_id"],
            )
            for r in rows
        ]

    bucket_expr = _trend_bucket_expr(trend_interval)
    rows = db.execute(sa.text(f"""
        WITH bucketed AS (
            SELECT
                {bucket_expr} AS bucket_start,
                played_at,
                rating_after
            FROM user_analytics_match_applied
            WHERE user_id=:u
              AND ladder_code=:l
              AND rating_after IS NOT NULL
        ),
        latest AS (
            SELECT DISTINCT ON (bucket_start)
                bucket_start,
                played_at,
                rating_after
            FROM bucketed
            ORDER BY bucket_start DESC, played_at DESC
        ),
        limited AS (
            SELECT bucket_start, rating_after
            FROM latest
            ORDER BY bucket_start DESC
            LIMIT :limit
        )
        SELECT
            bucket_start AS at,
            rating_after AS rating
        FROM limited
        ORDER BY at ASC
    """), params).mappings().all()
    return [
        RatingTrendPointOut(
            at=r["at"],
            rating=int(r["rating"]) if r["rating"] is not None else None,
            match_id=None,
        )
        for r in rows
    ]


def _query_rolling_win_rate(
    db: Session,
    *,
    user_id: str,
    ladder_code: str,
    trend_interval: str,
    points: int,
) -> list[RollingWinRatePointOut]:
    params = {"u": user_id, "l": ladder_code, "limit": points}
    if trend_interval == "match":
        rows = db.execute(sa.text("""
            SELECT
                t.played_at AS at,
                t.rolling_10_win_rate,
                t.rolling_20_win_rate,
                t.rolling_50_win_rate
            FROM (
                SELECT played_at, rolling_10_win_rate, rolling_20_win_rate, rolling_50_win_rate, match_id
                FROM user_analytics_match_applied
                WHERE user_id=:u
                  AND ladder_code=:l
                ORDER BY played_at DESC, match_id DESC
                LIMIT :limit
            ) t
            ORDER BY t.played_at ASC
        """), params).mappings().all()
    else:
        bucket_expr = _trend_bucket_expr(trend_interval)
        rows = db.execute(sa.text(f"""
            WITH bucketed AS (
                SELECT
                    {bucket_expr} AS bucket_start,
                    played_at,
                    rolling_10_win_rate,
                    rolling_20_win_rate,
                    rolling_50_win_rate
                FROM user_analytics_match_applied
                WHERE user_id=:u
                  AND ladder_code=:l
            ),
            latest AS (
                SELECT DISTINCT ON (bucket_start)
                    bucket_start,
                    played_at,
                    rolling_10_win_rate,
                    rolling_20_win_rate,
                    rolling_50_win_rate
                FROM bucketed
                ORDER BY bucket_start DESC, played_at DESC
            ),
            limited AS (
                SELECT bucket_start, rolling_10_win_rate, rolling_20_win_rate, rolling_50_win_rate
                FROM latest
                ORDER BY bucket_start DESC
                LIMIT :limit
            )
            SELECT
                bucket_start AS at,
                rolling_10_win_rate,
                rolling_20_win_rate,
                rolling_50_win_rate
            FROM limited
            ORDER BY at ASC
        """), params).mappings().all()
    return [
        RollingWinRatePointOut(
            at=r["at"],
            rolling_10_win_rate=_to_float(r["rolling_10_win_rate"]) if r["rolling_10_win_rate"] is not None else None,
            rolling_20_win_rate=_to_float(r["rolling_20_win_rate"]) if r["rolling_20_win_rate"] is not None else None,
            rolling_50_win_rate=_to_float(r["rolling_50_win_rate"]) if r["rolling_50_win_rate"] is not None else None,
        )
        for r in rows
    ]


def _query_volume(
    db: Session,
    *,
    user_id: str,
    ladder_code: str,
    bucket: str,
    points: int,
) -> list[VolumePointOut]:
    bucket_expr = _trend_bucket_expr(bucket)
    rows = db.execute(sa.text(f"""
        WITH grouped AS (
            SELECT
                {bucket_expr} AS bucket_start,
                COUNT(*)::int AS matches
            FROM user_analytics_match_applied
            WHERE user_id=:u
              AND ladder_code=:l
            GROUP BY bucket_start
        ),
        limited AS (
            SELECT bucket_start, matches
            FROM grouped
            ORDER BY bucket_start DESC
            LIMIT :limit
        )
        SELECT
            bucket_start AS at,
            matches
        FROM limited
        ORDER BY at ASC
    """), {"u": user_id, "l": ladder_code, "limit": points}).mappings().all()
    return [VolumePointOut(at=r["at"], matches=int(r["matches"] or 0)) for r in rows]


def _query_streak_timeline(
    db: Session,
    *,
    user_id: str,
    ladder_code: str,
    points: int,
) -> list[StreakPointOut]:
    rows = db.execute(sa.text("""
        SELECT
            t.match_id::text AS match_id,
            t.played_at AS at,
            t.streak_type_after AS streak_type,
            t.streak_len_after AS streak_len
        FROM (
            SELECT match_id, played_at, streak_type_after, streak_len_after
            FROM user_analytics_match_applied
            WHERE user_id=:u
              AND ladder_code=:l
              AND streak_type_after IS NOT NULL
              AND streak_len_after IS NOT NULL
            ORDER BY played_at DESC, match_id DESC
            LIMIT :limit
        ) t
        ORDER BY t.played_at ASC, t.match_id ASC
    """), {"u": user_id, "l": ladder_code, "limit": points}).mappings().all()
    return [
        StreakPointOut(
            at=r["at"],
            match_id=r["match_id"],
            streak_type=r["streak_type"],
            streak_len=int(r["streak_len"] or 0),
        )
        for r in rows
    ]


def _query_top_partners(
    db: Session,
    *,
    user_id: str,
    ladder_code: str,
    top_n: int,
) -> list[PartnerStatOut]:
    rows = db.execute(sa.text("""
        SELECT
            s.partner_user_id::text AS partner_user_id,
            p.alias AS partner_alias,
            s.matches,
            s.wins,
            s.losses,
            s.win_rate,
            s.last_played_at
        FROM user_analytics_partner_stats s
        LEFT JOIN user_profiles p ON p.user_id = s.partner_user_id
        WHERE s.user_id=:u
          AND s.ladder_code=:l
        ORDER BY s.matches DESC, s.win_rate DESC, s.partner_user_id
        LIMIT :limit
    """), {"u": user_id, "l": ladder_code, "limit": top_n}).mappings().all()
    return [
        PartnerStatOut(
            partner_user_id=r["partner_user_id"],
            partner_alias=r["partner_alias"],
            matches=int(r["matches"] or 0),
            wins=int(r["wins"] or 0),
            losses=int(r["losses"] or 0),
            win_rate=_to_float(r["win_rate"]),
            last_played_at=r["last_played_at"],
        )
        for r in rows
    ]


def _query_top_rivals(
    db: Session,
    *,
    user_id: str,
    ladder_code: str,
    top_n: int,
) -> list[RivalStatOut]:
    rows = db.execute(sa.text("""
        SELECT
            s.rival_user_id::text AS rival_user_id,
            p.alias AS rival_alias,
            s.matches,
            s.wins,
            s.losses,
            s.win_rate,
            s.last_played_at
        FROM user_analytics_rival_stats s
        LEFT JOIN user_profiles p ON p.user_id = s.rival_user_id
        WHERE s.user_id=:u
          AND s.ladder_code=:l
        ORDER BY s.matches DESC, s.win_rate DESC, s.rival_user_id
        LIMIT :limit
    """), {"u": user_id, "l": ladder_code, "limit": top_n}).mappings().all()
    return [
        RivalStatOut(
            rival_user_id=r["rival_user_id"],
            rival_alias=r["rival_alias"],
            matches=int(r["matches"] or 0),
            wins=int(r["wins"] or 0),
            losses=int(r["losses"] or 0),
            win_rate=_to_float(r["win_rate"]),
            last_played_at=r["last_played_at"],
        )
        for r in rows
    ]


def _ensure_target_visible(db: Session, *, current_user_id: str, target_user_id: str):
    if current_user_id == target_user_id:
        return
    prof = db.execute(sa.text("""
        SELECT is_public
        FROM user_profiles
        WHERE user_id=:u
    """), {"u": target_user_id}).mappings().first()
    if not prof:
        raise HTTPException(404, "Usuario no encontrado")
    if not bool(prof["is_public"]):
        raise HTTPException(404, "Analitica no disponible")


def _dashboard_payload(
    db: Session,
    *,
    user_id: str,
    ladder_code: str,
    state: AnalyticsStateOut | AnalyticsPublicOut,
    trend_interval: str,
    points: int,
    top_n: int,
) -> dict[str, object]:
    return {
        "state": state,
        "rating_trend": _query_rating_trend(
            db,
            user_id=user_id,
            ladder_code=ladder_code,
            trend_interval=trend_interval,
            points=points,
        ),
        "rolling_win_rate_trend": _query_rolling_win_rate(
            db,
            user_id=user_id,
            ladder_code=ladder_code,
            trend_interval=trend_interval,
            points=points,
        ),
        "volume_weekly": _query_volume(
            db,
            user_id=user_id,
            ladder_code=ladder_code,
            bucket="week",
            points=points,
        ),
        "volume_monthly": _query_volume(
            db,
            user_id=user_id,
            ladder_code=ladder_code,
            bucket="month",
            points=points,
        ),
        "streak_timeline": _query_streak_timeline(
            db,
            user_id=user_id,
            ladder_code=ladder_code,
            points=points,
        ),
        "top_partners": _query_top_partners(
            db,
            user_id=user_id,
            ladder_code=ladder_code,
            top_n=top_n,
        ),
        "top_rivals": _query_top_rivals(
            db,
            user_id=user_id,
            ladder_code=ladder_code,
            top_n=top_n,
        ),
    }


@router.get("/me", response_model=list[AnalyticsStateOut])
def analytics_me(
    ladder: str | None = Query(default=None, description="HM|WM|MX"),
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = _query_states(db, str(current.id), _normalize_ladder(ladder))
    return [_private_state_out(r) for r in rows]


@router.get("/me/dashboard", response_model=list[AnalyticsDashboardOut])
def analytics_me_dashboard(
    ladder: str | None = Query(default=None, description="HM|WM|MX"),
    trend_interval: str = Query(default="match", description="match|week|month"),
    points: int = Query(default=50, ge=5, le=200),
    top_n: int = Query(default=5, ge=1, le=20),
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = _query_states(db, str(current.id), _normalize_ladder(ladder))
    interval = _normalize_trend_interval(trend_interval)
    out: list[AnalyticsDashboardOut] = []
    for r in rows:
        state = _private_state_out(r)
        out.append(AnalyticsDashboardOut(**_dashboard_payload(
            db,
            user_id=str(current.id),
            ladder_code=str(r["ladder_code"]),
            state=state,
            trend_interval=interval,
            points=points,
            top_n=top_n,
        )))
    return out


@router.get("/users/{user_id}", response_model=list[AnalyticsPublicOut])
def analytics_user_public(
    user_id: str,
    ladder: str | None = Query(default=None, description="HM|WM|MX"),
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target_user_id = _normalize_user_id(user_id)
    _ensure_target_visible(db, current_user_id=str(current.id), target_user_id=target_user_id)

    rows = _query_states(db, target_user_id, _normalize_ladder(ladder))
    return [_public_state_out(r) for r in rows]


@router.get("/users/{user_id}/dashboard", response_model=list[AnalyticsPublicDashboardOut])
def analytics_user_dashboard_public(
    user_id: str,
    ladder: str | None = Query(default=None, description="HM|WM|MX"),
    trend_interval: str = Query(default="match", description="match|week|month"),
    points: int = Query(default=50, ge=5, le=200),
    top_n: int = Query(default=5, ge=1, le=20),
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target_user_id = _normalize_user_id(user_id)
    _ensure_target_visible(db, current_user_id=str(current.id), target_user_id=target_user_id)

    rows = _query_states(db, target_user_id, _normalize_ladder(ladder))
    interval = _normalize_trend_interval(trend_interval)
    out: list[AnalyticsPublicDashboardOut] = []
    for r in rows:
        state = _public_state_out(r)
        out.append(AnalyticsPublicDashboardOut(**_dashboard_payload(
            db,
            user_id=target_user_id,
            ladder_code=str(r["ladder_code"]),
            state=state,
            trend_interval=interval,
            points=points,
            top_n=top_n,
        )))
    return out
