from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.orm import Session


MAX_RECENT_FORM = 20
MAX_ROLLING_FORM = 50
RIVAL_BUCKET_DELTA = 75


@dataclass
class _ParticipantResult:
    user_id: str
    team_no: int
    is_win: bool


@dataclass
class _RatingMeta:
    old_rating: int | None
    new_rating: int | None
    delta: int | None


@dataclass
class _VerifiedMatchContext:
    match_id: str
    ladder_code: str
    played_at: datetime
    is_close_match: bool
    participants: list[_ParticipantResult]


def _pct(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((part * 100.0) / total, 2)


def _quality_bucket(self_old: int | None, opponent_avg: int | None) -> str:
    if self_old is None or opponent_avg is None:
        return "similar"
    diff = opponent_avg - self_old
    if diff >= RIVAL_BUCKET_DELTA:
        return "stronger"
    if diff <= -RIVAL_BUCKET_DELTA:
        return "weaker"
    return "similar"


def _load_verified_match_context(db: Session, match_id: str) -> _VerifiedMatchContext | None:
    rows = db.execute(sa.text("""
        SELECT
            m.id::text as match_id,
            m.ladder_code,
            m.played_at,
            ms.winner_team_no,
            ms.score_json,
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
    score_json = rows[0]["score_json"] or {}
    sets = score_json.get("sets") if isinstance(score_json, dict) else []
    is_close_match = isinstance(sets, list) and len(sets) >= 3

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
        is_close_match=is_close_match,
        participants=participants,
    )


def _load_rating_map(db: Session, match_id: str, ladder_code: str, participant_ids: list[str]) -> dict[str, _RatingMeta]:
    ids_param = sa.bindparam("ids", expanding=True)
    rows = db.execute(
        sa.text("""
            SELECT user_id::text as user_id, old_rating, new_rating, delta
            FROM rating_events
            WHERE match_id=:m
              AND ladder_code=:l
              AND user_id::text IN :ids
        """).bindparams(ids_param),
        {"m": match_id, "l": ladder_code, "ids": participant_ids},
    ).mappings().all()

    out: dict[str, _RatingMeta] = {
        r["user_id"]: _RatingMeta(
            old_rating=int(r["old_rating"]) if r["old_rating"] is not None else None,
            new_rating=int(r["new_rating"]) if r["new_rating"] is not None else None,
            delta=int(r["delta"]) if r["delta"] is not None else None,
        )
        for r in rows
    }

    missing = [uid for uid in participant_ids if uid not in out]
    if missing:
        state_rows = db.execute(
            sa.text("""
                SELECT user_id::text as user_id, rating
                FROM user_ladder_state
                WHERE ladder_code=:l
                  AND user_id::text IN :ids
            """).bindparams(ids_param),
            {"l": ladder_code, "ids": missing},
        ).mappings().all()
        for r in state_rows:
            rating = int(r["rating"])
            out[r["user_id"]] = _RatingMeta(old_rating=rating, new_rating=rating, delta=0)
        for uid in missing:
            if uid not in out:
                out[uid] = _RatingMeta(old_rating=None, new_rating=None, delta=None)
    return out


def _upsert_partner_stats(
    db: Session,
    *,
    user_id: str,
    ladder_code: str,
    partner_user_id: str | None,
    is_win: bool,
    played_at: datetime,
):
    if not partner_user_id:
        return
    wins = 1 if is_win else 0
    losses = 0 if is_win else 1
    db.execute(sa.text("""
        INSERT INTO user_analytics_partner_stats (
            user_id, ladder_code, partner_user_id, matches, wins, losses, win_rate, last_played_at, updated_at
        )
        VALUES (:u, :l, :p, 1, :wins, :losses, :win_rate, :played_at, now())
        ON CONFLICT (user_id, ladder_code, partner_user_id) DO UPDATE
        SET matches = user_analytics_partner_stats.matches + 1,
            wins = user_analytics_partner_stats.wins + :wins,
            losses = user_analytics_partner_stats.losses + :losses,
            win_rate = ROUND(((user_analytics_partner_stats.wins + :wins) * 100.0) / (user_analytics_partner_stats.matches + 1), 2),
            last_played_at = CASE
                WHEN user_analytics_partner_stats.last_played_at IS NULL THEN :played_at
                ELSE GREATEST(user_analytics_partner_stats.last_played_at, :played_at)
            END,
            updated_at = now()
    """), {
        "u": user_id,
        "l": ladder_code,
        "p": partner_user_id,
        "wins": wins,
        "losses": losses,
        "win_rate": _pct(wins, 1),
        "played_at": played_at,
    })


def _upsert_rival_stats(
    db: Session,
    *,
    user_id: str,
    ladder_code: str,
    rival_user_id: str,
    is_win: bool,
    played_at: datetime,
):
    wins = 1 if is_win else 0
    losses = 0 if is_win else 1
    db.execute(sa.text("""
        INSERT INTO user_analytics_rival_stats (
            user_id, ladder_code, rival_user_id, matches, wins, losses, win_rate, last_played_at, updated_at
        )
        VALUES (:u, :l, :r, 1, :wins, :losses, :win_rate, :played_at, now())
        ON CONFLICT (user_id, ladder_code, rival_user_id) DO UPDATE
        SET matches = user_analytics_rival_stats.matches + 1,
            wins = user_analytics_rival_stats.wins + :wins,
            losses = user_analytics_rival_stats.losses + :losses,
            win_rate = ROUND(((user_analytics_rival_stats.wins + :wins) * 100.0) / (user_analytics_rival_stats.matches + 1), 2),
            last_played_at = CASE
                WHEN user_analytics_rival_stats.last_played_at IS NULL THEN :played_at
                ELSE GREATEST(user_analytics_rival_stats.last_played_at, :played_at)
            END,
            updated_at = now()
    """), {
        "u": user_id,
        "l": ladder_code,
        "r": rival_user_id,
        "wins": wins,
        "losses": losses,
        "win_rate": _pct(wins, 1),
        "played_at": played_at,
    })


def _load_activity_windows(db: Session, user_id: str, ladder_code: str, played_at: datetime) -> tuple[int, int, int]:
    cut_7 = played_at - timedelta(days=7)
    cut_30 = played_at - timedelta(days=30)
    cut_90 = played_at - timedelta(days=90)
    row = db.execute(sa.text("""
        SELECT
            COUNT(*) FILTER (WHERE played_at >= :cut_7 AND played_at <= :played_at) AS c7,
            COUNT(*) FILTER (WHERE played_at >= :cut_30 AND played_at <= :played_at) AS c30,
            COUNT(*) FILTER (WHERE played_at >= :cut_90 AND played_at <= :played_at) AS c90
        FROM user_analytics_match_applied
        WHERE user_id=:u
          AND ladder_code=:l
          AND played_at <= :played_at
    """), {
        "u": user_id,
        "l": ladder_code,
        "cut_7": cut_7,
        "cut_30": cut_30,
        "cut_90": cut_90,
        "played_at": played_at,
    }).mappings().first()
    return int(row["c7"] or 0), int(row["c30"] or 0), int(row["c90"] or 0)


def _apply_participant_result(
    db: Session,
    *,
    match_id: str,
    ladder_code: str,
    played_at: datetime,
    user_id: str,
    is_win: bool,
    is_close_match: bool,
    teammate_user_id: str | None,
    opponent_user_ids: list[str],
    opponent_avg_rating: int | None,
    quality_bucket: str,
    rating_before: int | None,
    rating_after: int | None,
    rating_delta: int | None,
    enforce_idempotency: bool,
):
    insert_params = {
        "u": user_id,
        "m": match_id,
        "l": ladder_code,
        "w": is_win,
        "close": is_close_match,
        "teammate": teammate_user_id,
        "opp_a": opponent_user_ids[0] if len(opponent_user_ids) > 0 else None,
        "opp_b": opponent_user_ids[1] if len(opponent_user_ids) > 1 else None,
        "opp_avg": opponent_avg_rating,
        "quality": quality_bucket,
        "rating_before": rating_before,
        "rating_after": rating_after,
        "rating_delta": rating_delta,
        "p": played_at,
    }
    if enforce_idempotency:
        inserted = db.execute(sa.text("""
            INSERT INTO user_analytics_match_applied (
                user_id, match_id, ladder_code, is_win, is_close_match,
                teammate_user_id, opponent_a_user_id, opponent_b_user_id,
                opponent_avg_rating, quality_bucket,
                rating_before, rating_after, rating_delta, played_at
            )
            VALUES (
                :u, :m, :l, :w, :close,
                :teammate, :opp_a, :opp_b,
                :opp_avg, :quality,
                :rating_before, :rating_after, :rating_delta, :p
            )
            ON CONFLICT (user_id, match_id) DO NOTHING
            RETURNING 1
        """), insert_params).first()
        if not inserted:
            return
    else:
        db.execute(sa.text("""
            INSERT INTO user_analytics_match_applied (
                user_id, match_id, ladder_code, is_win, is_close_match,
                teammate_user_id, opponent_a_user_id, opponent_b_user_id,
                opponent_avg_rating, quality_bucket,
                rating_before, rating_after, rating_delta, played_at
            )
            VALUES (
                :u, :m, :l, :w, :close,
                :teammate, :opp_a, :opp_b,
                :opp_avg, :quality,
                :rating_before, :rating_after, :rating_delta, :p
            )
            ON CONFLICT (user_id, match_id) DO NOTHING
        """), insert_params)

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
            rolling_bits_50,
            rolling_size_50,
            close_matches,
            vs_stronger_matches,
            vs_stronger_wins,
            vs_similar_matches,
            vs_similar_wins,
            vs_weaker_matches,
            vs_weaker_wins,
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
    prev_len = int(st["current_streak_len"] or 0)
    streak_len = prev_len + 1 if (prev_type == new_type and prev_len > 0) else 1

    best_win = int(st["best_win_streak"] or 0)
    best_loss = int(st["best_loss_streak"] or 0)
    if new_type == "W":
        best_win = max(best_win, streak_len)
    else:
        best_loss = max(best_loss, streak_len)

    old_recent_bits = int(st["recent_form_bits"] or 0)
    old_recent_size = int(st["recent_form_size"] or 0)
    new_recent_bits = ((old_recent_bits << 1) | (1 if is_win else 0)) & ((1 << MAX_RECENT_FORM) - 1)
    new_recent_size = min(old_recent_size + 1, MAX_RECENT_FORM)

    old_roll_bits = int(st["rolling_bits_50"] or 0)
    old_roll_size = int(st["rolling_size_50"] or 0)
    new_roll_bits = ((old_roll_bits << 1) | (1 if is_win else 0)) & ((1 << MAX_ROLLING_FORM) - 1)
    new_roll_size = min(old_roll_size + 1, MAX_ROLLING_FORM)

    recent_10_matches = min(new_recent_size, 10)
    recent_10_mask = (1 << recent_10_matches) - 1 if recent_10_matches > 0 else 0
    recent_10_wins = (new_recent_bits & recent_10_mask).bit_count()
    recent_10_win_rate = _pct(recent_10_wins, recent_10_matches)

    roll_5_n = min(new_roll_size, 5)
    roll_5_mask = (1 << roll_5_n) - 1 if roll_5_n > 0 else 0
    roll_5_wins = (new_roll_bits & roll_5_mask).bit_count()
    rolling_5_win_rate = _pct(roll_5_wins, roll_5_n)

    roll_20_n = min(new_roll_size, 20)
    roll_20_mask = (1 << roll_20_n) - 1 if roll_20_n > 0 else 0
    roll_20_wins = (new_roll_bits & roll_20_mask).bit_count()
    rolling_20_win_rate = _pct(roll_20_wins, roll_20_n)

    roll_50_n = min(new_roll_size, 50)
    roll_50_mask = (1 << roll_50_n) - 1 if roll_50_n > 0 else 0
    roll_50_wins = (new_roll_bits & roll_50_mask).bit_count()
    rolling_50_win_rate = _pct(roll_50_wins, roll_50_n)

    close_matches = int(st["close_matches"] or 0) + (1 if is_close_match else 0)
    close_match_rate = _pct(close_matches, total)

    vs_stronger_matches = int(st["vs_stronger_matches"] or 0)
    vs_stronger_wins = int(st["vs_stronger_wins"] or 0)
    vs_similar_matches = int(st["vs_similar_matches"] or 0)
    vs_similar_wins = int(st["vs_similar_wins"] or 0)
    vs_weaker_matches = int(st["vs_weaker_matches"] or 0)
    vs_weaker_wins = int(st["vs_weaker_wins"] or 0)

    if quality_bucket == "stronger":
        vs_stronger_matches += 1
        vs_stronger_wins += 1 if is_win else 0
    elif quality_bucket == "weaker":
        vs_weaker_matches += 1
        vs_weaker_wins += 1 if is_win else 0
    else:
        vs_similar_matches += 1
        vs_similar_wins += 1 if is_win else 0

    vs_stronger_win_rate = _pct(vs_stronger_wins, vs_stronger_matches)
    vs_similar_win_rate = _pct(vs_similar_wins, vs_similar_matches)
    vs_weaker_win_rate = _pct(vs_weaker_wins, vs_weaker_matches)

    matches_7d, matches_30d, matches_90d = _load_activity_windows(db, user_id, ladder_code, played_at)

    current_rating = rating_after
    if current_rating is None:
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
            rolling_bits_50=:rolling_bits_50,
            rolling_size_50=:rolling_size_50,
            rolling_5_win_rate=:rolling_5_win_rate,
            rolling_20_win_rate=:rolling_20_win_rate,
            rolling_50_win_rate=:rolling_50_win_rate,
            matches_7d=:matches_7d,
            matches_30d=:matches_30d,
            matches_90d=:matches_90d,
            close_matches=:close_matches,
            close_match_rate=:close_match_rate,
            vs_stronger_matches=:vs_stronger_matches,
            vs_stronger_wins=:vs_stronger_wins,
            vs_stronger_win_rate=:vs_stronger_win_rate,
            vs_similar_matches=:vs_similar_matches,
            vs_similar_wins=:vs_similar_wins,
            vs_similar_win_rate=:vs_similar_win_rate,
            vs_weaker_matches=:vs_weaker_matches,
            vs_weaker_wins=:vs_weaker_wins,
            vs_weaker_win_rate=:vs_weaker_win_rate,
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
        "recent_bits": new_recent_bits,
        "recent_size": new_recent_size,
        "recent_10_matches": recent_10_matches,
        "recent_10_wins": recent_10_wins,
        "recent_10_win_rate": recent_10_win_rate,
        "rolling_bits_50": new_roll_bits,
        "rolling_size_50": new_roll_size,
        "rolling_5_win_rate": rolling_5_win_rate,
        "rolling_20_win_rate": rolling_20_win_rate,
        "rolling_50_win_rate": rolling_50_win_rate,
        "matches_7d": matches_7d,
        "matches_30d": matches_30d,
        "matches_90d": matches_90d,
        "close_matches": close_matches,
        "close_match_rate": close_match_rate,
        "vs_stronger_matches": vs_stronger_matches,
        "vs_stronger_wins": vs_stronger_wins,
        "vs_stronger_win_rate": vs_stronger_win_rate,
        "vs_similar_matches": vs_similar_matches,
        "vs_similar_wins": vs_similar_wins,
        "vs_similar_win_rate": vs_similar_win_rate,
        "vs_weaker_matches": vs_weaker_matches,
        "vs_weaker_wins": vs_weaker_wins,
        "vs_weaker_win_rate": vs_weaker_win_rate,
        "current_rating": current_rating,
        "peak_rating": peak_rating,
        "match_id": match_id,
        "played_at": played_at,
    })

    db.execute(sa.text("""
        UPDATE user_analytics_match_applied
        SET rolling_10_win_rate=:rolling_10_win_rate,
            rolling_20_win_rate=:rolling_20_win_rate,
            rolling_50_win_rate=:rolling_50_win_rate,
            streak_type_after=:streak_type_after,
            streak_len_after=:streak_len_after
        WHERE user_id=:u AND match_id=:m
    """), {
        "u": user_id,
        "m": match_id,
        "rolling_10_win_rate": recent_10_win_rate,
        "rolling_20_win_rate": rolling_20_win_rate,
        "rolling_50_win_rate": rolling_50_win_rate,
        "streak_type_after": new_type,
        "streak_len_after": streak_len,
    })

    _upsert_partner_stats(
        db,
        user_id=user_id,
        ladder_code=ladder_code,
        partner_user_id=teammate_user_id,
        is_win=is_win,
        played_at=played_at,
    )
    for rival_user_id in sorted(set(opponent_user_ids)):
        _upsert_rival_stats(
            db,
            user_id=user_id,
            ladder_code=ladder_code,
            rival_user_id=rival_user_id,
            is_win=is_win,
            played_at=played_at,
        )


def apply_verified_match_analytics(db: Session, match_id: str):
    ctx = _load_verified_match_context(db, match_id)
    if not ctx:
        return

    participant_ids = [p.user_id for p in ctx.participants]
    ratings = _load_rating_map(db, ctx.match_id, ctx.ladder_code, participant_ids)
    by_team: dict[int, list[str]] = defaultdict(list)
    for p in ctx.participants:
        by_team[p.team_no].append(p.user_id)

    for p in ctx.participants:
        teammates = [uid for uid in by_team[p.team_no] if uid != p.user_id]
        opponents = [uid for tno, ids in by_team.items() if tno != p.team_no for uid in ids]
        opp_old = [ratings[uid].old_rating for uid in opponents if ratings.get(uid) and ratings[uid].old_rating is not None]
        opp_avg = int(round(sum(opp_old) / len(opp_old))) if opp_old else None
        self_meta = ratings.get(p.user_id)
        quality = _quality_bucket(self_meta.old_rating if self_meta else None, opp_avg)

        _apply_participant_result(
            db,
            match_id=ctx.match_id,
            ladder_code=ctx.ladder_code,
            played_at=ctx.played_at,
            user_id=p.user_id,
            is_win=p.is_win,
            is_close_match=ctx.is_close_match,
            teammate_user_id=teammates[0] if teammates else None,
            opponent_user_ids=opponents[:2],
            opponent_avg_rating=opp_avg,
            quality_bucket=quality,
            rating_before=self_meta.old_rating if self_meta else None,
            rating_after=self_meta.new_rating if self_meta else None,
            rating_delta=self_meta.delta if self_meta else None,
            enforce_idempotency=True,
        )


def rebuild_analytics(db: Session):
    db.execute(sa.text("DELETE FROM user_analytics_rival_stats"))
    db.execute(sa.text("DELETE FROM user_analytics_partner_stats"))
    db.execute(sa.text("DELETE FROM user_analytics_match_applied"))
    db.execute(sa.text("DELETE FROM user_analytics_state"))

    rows = db.execute(sa.text("""
        SELECT
            m.id::text as match_id,
            m.ladder_code,
            m.played_at,
            ms.winner_team_no,
            ms.score_json,
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
        score_json = r["score_json"] or {}
        sets = score_json.get("sets") if isinstance(score_json, dict) else []
        g["is_close_match"] = isinstance(sets, list) and len(sets) >= 3
        g["participants"].append((r["user_id"], int(r["team_no"])))

    for g in grouped.values():
        participant_ids = [uid for uid, _ in g["participants"]]
        ratings = _load_rating_map(db, g["match_id"], g["ladder_code"], participant_ids)
        by_team: dict[int, list[str]] = defaultdict(list)
        for uid, team_no in g["participants"]:
            by_team[team_no].append(uid)

        for user_id, team_no in g["participants"]:
            is_win = team_no == g["winner_team_no"]
            teammates = [uid for uid in by_team[team_no] if uid != user_id]
            opponents = [uid for tno, ids in by_team.items() if tno != team_no for uid in ids]
            opp_old = [ratings[uid].old_rating for uid in opponents if ratings.get(uid) and ratings[uid].old_rating is not None]
            opp_avg = int(round(sum(opp_old) / len(opp_old))) if opp_old else None
            self_meta = ratings.get(user_id)
            quality = _quality_bucket(self_meta.old_rating if self_meta else None, opp_avg)

            _apply_participant_result(
                db,
                match_id=g["match_id"],
                ladder_code=g["ladder_code"],
                played_at=g["played_at"],
                user_id=user_id,
                is_win=is_win,
                is_close_match=bool(g.get("is_close_match")),
                teammate_user_id=teammates[0] if teammates else None,
                opponent_user_ids=opponents[:2],
                opponent_avg_rating=opp_avg,
                quality_bucket=quality,
                rating_before=self_meta.old_rating if self_meta else None,
                rating_after=self_meta.new_rating if self_meta else None,
                rating_delta=self_meta.delta if self_meta else None,
                enforce_idempotency=False,
            )
