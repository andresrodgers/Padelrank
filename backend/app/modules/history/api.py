from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.schemas.history import (
    HistoryMatchDetailOut,
    HistoryParticipantOut,
    HistoryScoreOut,
    HistoryTimelineItemOut,
    HistoryTimelineOut,
)

router = APIRouter()

_VALID_LADDERS = {"HM", "WM", "MX"}
_EFFECTIVE_STATUS_SQL = """
CASE
  WHEN m.status='pending_confirm' AND m.confirmation_deadline < now() THEN 'expired'
  ELSE m.status
END
"""
_STATUS_REASON_SQL = f"""
CASE
  WHEN {_EFFECTIVE_STATUS_SQL}='verified' THEN 'confirmed_by_both_teams'
  WHEN {_EFFECTIVE_STATUS_SQL}='pending_confirm' THEN 'awaiting_confirmations'
  WHEN {_EFFECTIVE_STATUS_SQL}='expired' THEN 'confirmation_window_elapsed'
  WHEN {_EFFECTIVE_STATUS_SQL}='disputed' THEN 'dispute_open'
  WHEN {_EFFECTIVE_STATUS_SQL}='void' THEN 'voided'
  ELSE 'unknown_status'
END
"""
_RANKING_IMPACT_SQL = f"(({_EFFECTIVE_STATUS_SQL}='verified') AND m.rank_processed_at IS NOT NULL)"
_RANKING_IMPACT_REASON_SQL = f"""
CASE
  WHEN {_EFFECTIVE_STATUS_SQL}='verified' AND m.rank_processed_at IS NOT NULL THEN 'verified_and_processed'
  WHEN {_EFFECTIVE_STATUS_SQL}='verified' AND m.rank_processed_at IS NULL THEN 'verified_pending_processing'
  WHEN {_EFFECTIVE_STATUS_SQL}='pending_confirm' THEN 'not_verified'
  WHEN {_EFFECTIVE_STATUS_SQL}='expired' THEN 'expired_unconfirmed'
  WHEN {_EFFECTIVE_STATUS_SQL}='disputed' THEN 'disputed_match'
  WHEN {_EFFECTIVE_STATUS_SQL}='void' THEN 'void_match'
  ELSE 'unknown'
END
"""


def _normalize_uuid(raw: str, name: str) -> str:
    try:
        return str(UUID(raw))
    except Exception:
        raise HTTPException(400, f"Invalid {name}")


def _normalize_ladder(ladder: str | None) -> str | None:
    if ladder is None:
        return None
    out = ladder.strip().upper()
    if out not in _VALID_LADDERS:
        raise HTTPException(400, "ladder must be HM|WM|MX")
    return out


def _resolve_timeline_scope(scope: Literal["verified", "pending", "all"], is_self: bool) -> Literal["verified", "pending", "all"]:
    if is_self:
        return scope
    if scope != "verified":
        raise HTTPException(403, "state_scope pending/all is only allowed for self history")
    return "verified"


def _load_profile_visibility(db: Session, target_user_id: str) -> bool:
    row = db.execute(sa.text("""
        SELECT is_public
        FROM user_profiles
        WHERE user_id=:u
    """), {"u": target_user_id}).mappings().first()
    if not row:
        raise HTTPException(404, "User not found")
    return bool(row["is_public"])


def _timeline_where_for_scope(scope: Literal["verified", "pending", "all"]) -> str:
    if scope == "verified":
        return "m.status='verified'"
    if scope == "pending":
        return "(m.status='pending_confirm' AND m.confirmation_deadline >= now())"
    return "(m.status='verified' OR (m.status='pending_confirm' AND m.confirmation_deadline >= now()))"


def _query_timeline(
    db: Session,
    *,
    target_user_id: str,
    visibility_reason: str,
    ladder: str | None,
    date_from: date | None,
    date_to: date | None,
    state_scope: Literal["verified", "pending", "all"],
    club_id: str | None,
    club_city: str | None,
    limit: int,
    offset: int,
    match_id: str | None = None,
):
    where = [
        "1=1",
        _timeline_where_for_scope(state_scope),
    ]
    params: dict[str, object] = {
        "target_user_id": target_user_id,
        "visibility_reason": visibility_reason,
        "limit": limit,
        "offset": offset,
    }

    if ladder is not None:
        where.append("m.ladder_code=:ladder")
        params["ladder"] = ladder
    if date_from is not None:
        where.append("m.played_at >= CAST(:date_from AS date)")
        params["date_from"] = date_from
    if date_to is not None:
        where.append("m.played_at < (CAST(:date_to AS date) + interval '1 day')")
        params["date_to"] = date_to
    if club_id is not None:
        where.append("m.club_id=:club_id")
        params["club_id"] = _normalize_uuid(club_id, "club_id")
    if club_city is not None:
        city = club_city.strip()
        if not city:
            raise HTTPException(400, "club_city cannot be empty")
        where.append("lower(cl.city)=lower(:club_city)")
        params["club_city"] = city
    if match_id is not None:
        where.append("m.id=:match_id")
        params["match_id"] = _normalize_uuid(match_id, "match_id")

    rows = db.execute(sa.text(f"""
        WITH user_matches AS (
            SELECT match_id, team_no
            FROM match_participants
            WHERE user_id=:target_user_id
        )
        SELECT
            m.id::text as match_id,
            m.ladder_code,
            m.category_id::text as category_id,
            c.code as category_code,
            m.club_id::text as club_id,
            cl.name as club_name,
            cl.city as club_city,
            m.played_at,
            m.created_at,
            m.confirmation_deadline,
            m.confirmed_count,
            m.has_dispute,
            {_EFFECTIVE_STATUS_SQL} as status,
            {_STATUS_REASON_SQL} as status_reason,
            :visibility_reason as visibility_reason,
            {_RANKING_IMPACT_SQL} as ranking_impact,
            {_RANKING_IMPACT_REASON_SQL} as ranking_impact_reason,
            um.team_no as focus_team_no,
            COALESCE(
                ARRAY(
                    SELECT up.alias
                    FROM match_participants mp2
                    JOIN user_profiles up ON up.user_id = mp2.user_id
                    WHERE mp2.match_id = m.id
                      AND mp2.team_no <> um.team_no
                    ORDER BY up.alias
                ),
                ARRAY[]::text[]
            ) as rival_aliases,
            ms.winner_team_no as winner_team_no,
            CASE
                WHEN ms.winner_team_no IS NULL THEN NULL
                WHEN ms.winner_team_no = um.team_no THEN true
                ELSE false
            END as did_focus_user_win,
            m.created_by::text as created_by,
            cp.alias as created_by_alias
        FROM user_matches um
        JOIN matches m ON m.id = um.match_id
        JOIN categories c ON c.id = m.category_id
        LEFT JOIN clubs cl ON cl.id = m.club_id
        LEFT JOIN match_scores ms ON ms.match_id = m.id
        LEFT JOIN user_profiles cp ON cp.user_id = m.created_by
        WHERE {" AND ".join(where)}
        ORDER BY m.played_at DESC, m.created_at DESC
        LIMIT :limit OFFSET :offset
    """), params).mappings().all()

    out_rows = [
        HistoryTimelineItemOut(
            **{
                **r,
                "rival_aliases": list(r["rival_aliases"] or []),
            }
        )
        for r in rows
    ]
    next_offset = (offset + limit) if len(out_rows) == limit else None
    return out_rows, next_offset


@router.get("/me", response_model=HistoryTimelineOut)
def history_me(
    ladder: str | None = Query(default=None, description="HM|WM|MX"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    state_scope: Literal["verified", "pending", "all"] = Query(default="verified"),
    club_id: str | None = Query(default=None),
    club_city: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(400, "date_from cannot be greater than date_to")

    rows, next_offset = _query_timeline(
        db,
        target_user_id=str(current.id),
        visibility_reason="self_participant",
        ladder=_normalize_ladder(ladder),
        date_from=date_from,
        date_to=date_to,
        state_scope=state_scope,
        club_id=club_id,
        club_city=club_city,
        limit=limit,
        offset=offset,
    )
    return HistoryTimelineOut(
        target_user_id=str(current.id),
        rows=rows,
        limit=limit,
        offset=offset,
        next_offset=next_offset,
    )


@router.get("/users/{user_id}", response_model=HistoryTimelineOut)
def history_user(
    user_id: str,
    ladder: str | None = Query(default=None, description="HM|WM|MX"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    state_scope: Literal["verified", "pending", "all"] = Query(default="verified"),
    club_id: str | None = Query(default=None),
    club_city: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(400, "date_from cannot be greater than date_to")

    target_user_id = _normalize_uuid(user_id, "user_id")
    is_self = str(current.id) == target_user_id
    is_public = _load_profile_visibility(db, target_user_id)

    if not is_self and not is_public:
        raise HTTPException(404, "User history not available")

    effective_scope = _resolve_timeline_scope(state_scope, is_self)
    visibility_reason = "self_participant" if is_self else "public_verified_history"

    rows, next_offset = _query_timeline(
        db,
        target_user_id=target_user_id,
        visibility_reason=visibility_reason,
        ladder=_normalize_ladder(ladder),
        date_from=date_from,
        date_to=date_to,
        state_scope=effective_scope,
        club_id=club_id,
        club_city=club_city,
        limit=limit,
        offset=offset,
    )
    return HistoryTimelineOut(
        target_user_id=target_user_id,
        rows=rows,
        limit=limit,
        offset=offset,
        next_offset=next_offset,
    )


@router.get("/users/{user_id}/matches/{match_id}", response_model=HistoryMatchDetailOut)
def history_match_detail(
    user_id: str,
    match_id: str,
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target_user_id = _normalize_uuid(user_id, "user_id")
    is_self = str(current.id) == target_user_id
    is_public = _load_profile_visibility(db, target_user_id)
    if not is_self and not is_public:
        raise HTTPException(404, "User history not available")

    visibility_reason = "self_participant" if is_self else "public_verified_history"
    state_scope: Literal["verified", "pending", "all"] = "all" if is_self else "verified"
    rows, _ = _query_timeline(
        db,
        target_user_id=target_user_id,
        visibility_reason=visibility_reason,
        ladder=None,
        date_from=None,
        date_to=None,
        state_scope=state_scope,
        club_id=None,
        club_city=None,
        limit=1,
        offset=0,
        match_id=match_id,
    )
    if not rows:
        raise HTTPException(404, "History event not found")
    event = rows[0]

    parts = db.execute(sa.text("""
        SELECT
            mp.user_id::text as user_id,
            up.alias as alias,
            up.gender as gender,
            mp.team_no as team_no,
            COALESCE(mc.status, 'pending') as confirmation_status,
            mc.decided_at as decided_at
        FROM match_participants mp
        JOIN user_profiles up ON up.user_id = mp.user_id
        LEFT JOIN match_confirmations mc
          ON mc.match_id = mp.match_id AND mc.user_id = mp.user_id
        WHERE mp.match_id=:m
        ORDER BY mp.team_no, up.alias
    """), {"m": _normalize_uuid(match_id, "match_id")}).mappings().all()
    participants = [HistoryParticipantOut(**p) for p in parts]

    focus_team = event.focus_team_no
    teammate_aliases = [
        p.alias for p in participants
        if p.team_no == focus_team and p.user_id != target_user_id
    ]
    rival_aliases = [p.alias for p in participants if p.team_no != focus_team]

    score_row = db.execute(sa.text("""
        SELECT score_json, winner_team_no
        FROM match_scores
        WHERE match_id=:m
    """), {"m": _normalize_uuid(match_id, "match_id")}).mappings().first()
    score = HistoryScoreOut(**score_row) if score_row else None

    return HistoryMatchDetailOut(
        focus_user_id=target_user_id,
        event=event,
        participants=participants,
        teammate_aliases=teammate_aliases,
        rival_aliases=rival_aliases,
        score=score,
    )
