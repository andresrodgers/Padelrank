from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session


MAX_RECENT_FORM = 20


@dataclass
class _ParticipantResult:
    user_id: str
    team_no: int
    is_win: bool


@dataclass
class _VerifiedMatchContext:
    match_id: str
    ladder_code: str
    played_at: datetime
    participants: list[_ParticipantResult]


def _pct(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((part * 100.0) / total, 2)


def _to_float(value) -> float:
    if value is None:
        return 0.0
    return float(value)


def _load_verified_match_context(db: Session, match_id: str) -> _VerifiedMatchContext | None:
    rows = db.execute(sa.text("""
        SELECT
            m.id::text as match_id,
            m.ladder_code,
            m.played_at,
            ms.winner_team_no,
            mp.user_id::text as user_id,
            mp.team_no
        FROM matches m
        JOIN match_scores ms ON ms.match_id = m.id
        JOIN match_participants mp ON mp.match_id = m.id
        WHERE m.id=:m
          AND m.status='verified'
        ORDER BY mp.team_no, mp.user_id
    """), {"m": match_id}).mappings().all()
    if not rows:
        return None

    winner_team_no = int(rows[0]["winner_team_no"])
    participants = [
        _ParticipantResult(
            user_id=r["user_id"],
            team_no=int(r["team_no"]),
            is_win=(int(r["team_no"]) == winner_team_no),
        )
        for r in rows
    ]
    return _VerifiedMatchContext(
        match_id=rows[0]["match_id"],
        ladder_code=rows[0]["ladder_code"],
        played_at=rows[0]["played_at"],
        participants=participants,
    )


def _apply_participant_result(
    db: Session,
    *,
    match_id: str,
    ladder_code: str,
    played_at: datetime,
    user_id: str,
    is_win: bool,
    enforce_idempotency: bool,
):
    if enforce_idempotency:
        inserted = db.execute(sa.text("""
            INSERT INTO user_analytics_match_applied (user_id, match_id, ladder_code, is_win, played_at)
            VALUES (:u, :m, :l, :w, :p)
            ON CONFLICT (user_id, match_id) DO NOTHING
            RETURNING 1
        """), {"u": user_id, "m": match_id, "l": ladder_code, "w": is_win, "p": played_at}).first()
        if not inserted:
            return
    else:
        db.execute(sa.text("""
            INSERT INTO user_analytics_match_applied (user_id, match_id, ladder_code, is_win, played_at)
            VALUES (:u, :m, :l, :w, :p)
            ON CONFLICT (user_id, match_id) DO NOTHING
        """), {"u": user_id, "m": match_id, "l": ladder_code, "w": is_win, "p": played_at})

    db.execute(sa.text("""
        INSERT INTO user_analytics_state (user_id, ladder_code)
        VALUES (:u, :l)
        ON CONFLICT (user_id, ladder_code) DO NOTHING
    """), {"u": user_id, "l": ladder_code})

    st = db.execute(sa.text("""
        SELECT
            total_verified_matches,
            wins,
            losses,
            current_streak_type,
            current_streak_len,
            best_win_streak,
            best_loss_streak,
            recent_form_bits,
            recent_form_size,
            peak_rating
        FROM user_analytics_state
        WHERE user_id=:u AND ladder_code=:l
        FOR UPDATE
    """), {"u": user_id, "l": ladder_code}).mappings().first()
    if not st:
        return

    total = int(st["total_verified_matches"]) + 1
    wins = int(st["wins"]) + (1 if is_win else 0)
    losses = int(st["losses"]) + (0 if is_win else 1)
    win_rate = _pct(wins, total)

    new_type = "W" if is_win else "L"
    prev_type = st["current_streak_type"]
    prev_len = int(st["current_streak_len"])
    if prev_type == new_type and prev_len > 0:
        streak_len = prev_len + 1
    else:
        streak_len = 1
    best_win = int(st["best_win_streak"])
    best_loss = int(st["best_loss_streak"])
    if new_type == "W":
        best_win = max(best_win, streak_len)
    else:
        best_loss = max(best_loss, streak_len)

    old_bits = int(st["recent_form_bits"] or 0)
    old_size = int(st["recent_form_size"] or 0)
    new_bits = ((old_bits << 1) | (1 if is_win else 0)) & ((1 << MAX_RECENT_FORM) - 1)
    new_size = min(old_size + 1, MAX_RECENT_FORM)

    recent_10_matches = min(new_size, 10)
    recent_10_mask = (1 << recent_10_matches) - 1 if recent_10_matches > 0 else 0
    recent_10_wins = (new_bits & recent_10_mask).bit_count()
    recent_10_win_rate = _pct(recent_10_wins, recent_10_matches)

    rating_row = db.execute(sa.text("""
        SELECT rating
        FROM user_ladder_state
        WHERE user_id=:u AND ladder_code=:l
    """), {"u": user_id, "l": ladder_code}).mappings().first()
    current_rating = int(rating_row["rating"]) if rating_row else None
    peak_rating = int(st["peak_rating"]) if st["peak_rating"] is not None else None
    if current_rating is not None:
        peak_rating = current_rating if peak_rating is None else max(peak_rating, current_rating)

    db.execute(sa.text("""
        UPDATE user_analytics_state
        SET total_verified_matches=:total,
            wins=:wins,
            losses=:losses,
            win_rate=:win_rate,
            current_streak_type=:streak_type,
            current_streak_len=:streak_len,
            best_win_streak=:best_win,
            best_loss_streak=:best_loss,
            recent_form_bits=:recent_bits,
            recent_form_size=:recent_size,
            recent_10_matches=:recent_10_matches,
            recent_10_wins=:recent_10_wins,
            recent_10_win_rate=:recent_10_win_rate,
            current_rating=:current_rating,
            peak_rating=:peak_rating,
            last_match_id=:match_id,
            last_match_at=:played_at,
            updated_at=now()
        WHERE user_id=:u AND ladder_code=:l
    """), {
        "u": user_id,
        "l": ladder_code,
        "total": total,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "streak_type": new_type,
        "streak_len": streak_len,
        "best_win": best_win,
        "best_loss": best_loss,
        "recent_bits": new_bits,
        "recent_size": new_size,
        "recent_10_matches": recent_10_matches,
        "recent_10_wins": recent_10_wins,
        "recent_10_win_rate": recent_10_win_rate,
        "current_rating": current_rating,
        "peak_rating": peak_rating,
        "match_id": match_id,
        "played_at": played_at,
    })


def apply_verified_match_analytics(db: Session, match_id: str):
    ctx = _load_verified_match_context(db, match_id)
    if not ctx:
        return
    for p in ctx.participants:
        _apply_participant_result(
            db,
            match_id=ctx.match_id,
            ladder_code=ctx.ladder_code,
            played_at=ctx.played_at,
            user_id=p.user_id,
            is_win=p.is_win,
            enforce_idempotency=True,
        )


def rebuild_analytics(db: Session):
    db.execute(sa.text("DELETE FROM user_analytics_match_applied"))
    db.execute(sa.text("DELETE FROM user_analytics_state"))

    rows = db.execute(sa.text("""
        SELECT
            m.id::text as match_id,
            m.ladder_code,
            m.played_at,
            ms.winner_team_no,
            mp.user_id::text as user_id,
            mp.team_no
        FROM matches m
        JOIN match_scores ms ON ms.match_id = m.id
        JOIN match_participants mp ON mp.match_id = m.id
        WHERE m.status='verified'
        ORDER BY m.played_at, m.created_at, m.id, mp.team_no, mp.user_id
    """)).mappings().all()

    grouped: dict[str, dict] = defaultdict(lambda: {"participants": []})
    for r in rows:
        g = grouped[r["match_id"]]
        g["match_id"] = r["match_id"]
        g["ladder_code"] = r["ladder_code"]
        g["played_at"] = r["played_at"]
        g["winner_team_no"] = int(r["winner_team_no"])
        g["participants"].append((r["user_id"], int(r["team_no"])))

    for g in grouped.values():
        for user_id, team_no in g["participants"]:
            _apply_participant_result(
                db,
                match_id=g["match_id"],
                ladder_code=g["ladder_code"],
                played_at=g["played_at"],
                user_id=user_id,
                is_win=(team_no == g["winner_team_no"]),
                enforce_idempotency=False,
            )
