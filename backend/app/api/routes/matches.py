from datetime import timedelta
import json
import math
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import sqlalchemy as sa

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import now_utc
from app.db.session import get_db
from app.services.audit import audit
from app.services.elo import compute_elo

from app.services.score_features import extract_score_features, mov_weight_from_features

from app.schemas.match import (
    MatchCreateIn, MatchOut, ConfirmIn,
    MatchConfirmationsOut, MatchConfirmationRowOut,
    MatchDetailOut, MatchParticipantOut, MatchScoreOut,
)

router = APIRouter()

def _assert_is_participant(db: Session, match_id: str, user_id: str):
    ok = db.execute(sa.text("""
        SELECT 1
        FROM match_participants
        WHERE match_id=:m AND user_id=:u
    """), {"m": match_id, "u": user_id}).first()
    if not ok:
        raise HTTPException(403, "Not a participant")

def _assert_block_rules(db: Session, user_id):
    pending = db.execute(sa.text("""
        SELECT count(*) FROM matches
        WHERE created_by=:u AND status='pending_confirm' AND now()<=confirmation_deadline
    """), {"u": user_id}).scalar_one()
    expired = db.execute(sa.text("""
        SELECT count(*) FROM matches
        WHERE created_by=:u AND status='expired' AND confirmation_deadline < now() AND created_at >= (now() - interval '30 days')
    """), {"u": user_id}).scalar_one()

    if pending >= 2 or expired >= 1:
        raise HTTPException(403, "Blocked from creating new match (pending/expired limit)")

def _fetch_profiles(db: Session, participant_ids: list[UUID]):
    rows = db.execute(sa.text("""
        SELECT user_id::text as user_id, gender
        FROM user_profiles
        WHERE user_id = ANY(:ids)
    """), {"ids": participant_ids}).mappings().all()
    if len(rows) != 4:
        raise HTTPException(400, "All participants must have profiles")
    if any(r["gender"] not in ("M", "F") for r in rows):
        raise HTTPException(400, "Participants must have gender M/F")
    return rows

def _determine_ladder_from_genders(genders: list[str]) -> str:
    m = genders.count("M")
    f = genders.count("F")
    if m == 4 and f == 0:
        return "HM"
    if f == 4 and m == 0:
        return "WM"
    if m == 2 and f == 2:
        return "MX"
    raise HTTPException(400, "Invalid gender mix. Use 4M (HM), 4F (WM) or 2M2F (MX)")

def _require_ladder_states(db: Session, ladder_code: str, participant_ids: list[UUID]):
    cnt = int(db.execute(sa.text("""
        SELECT count(*)
        FROM user_ladder_state
        WHERE ladder_code=:l AND user_id = ANY(:ids)
    """), {"l": ladder_code, "ids": participant_ids}).scalar_one())
    if cnt != 4:
        raise HTTPException(400, f"All participants must have ladder state for {ladder_code}. Complete profile (category) first.")

def _derive_match_category_id(db: Session, ladder_code: str, participants, participant_ids: list[UUID]) -> str:
    # HM/WM: categoría del partido = jugador más fuerte (anti-sandbagging) => min sort_order
    if ladder_code in ("HM", "WM"):
        rows = db.execute(sa.text("""
            SELECT s.user_id::text as user_id, c.sort_order
            FROM user_ladder_state s
            JOIN categories c ON c.id=s.category_id
            WHERE s.ladder_code=:l AND s.user_id = ANY(:ids)
        """), {"l": ladder_code, "ids": participant_ids}).mappings().all()
        if len(rows) != 4:
            raise HTTPException(400, "Missing ladder state/category for participants")

        min_sort = min(int(r["sort_order"]) for r in rows)
        cat = db.execute(sa.text("""
            SELECT id::text as id
            FROM categories
            WHERE ladder_code=:l AND sort_order=:o
            LIMIT 1
        """), {"l": ladder_code, "o": min_sort}).mappings().first()
        if not cat:
            raise HTTPException(400, "Could not derive match category")
        return cat["id"]

    # MX: se calcula por equipo (promedio y techo), y el equipo más fuerte define la categoría del match
    if ladder_code == "MX":
        rows = db.execute(sa.text("""
            SELECT s.user_id::text as user_id, c.sort_order
            FROM user_ladder_state s
            JOIN categories c ON c.id=s.category_id
            WHERE s.ladder_code='MX' AND s.user_id = ANY(:ids)
        """), {"ids": participant_ids}).mappings().all()
        if len(rows) != 4:
            raise HTTPException(400, "Missing MX ladder state/category for participants")

        score_by_user = {r["user_id"]: int(r["sort_order"]) for r in rows}

        t1 = [p for p in participants if p.team_no == 1]
        t2 = [p for p in participants if p.team_no == 2]
        if len(t1) != 2 or len(t2) != 2:
            raise HTTPException(400, "Each team must have 2 participants")

        def team_score(team_parts):
            s1 = score_by_user[team_parts[0].user_id]
            s2 = score_by_user[team_parts[1].user_id]
            return int(math.ceil((s1 + s2) / 2.0))

        team1_score = team_score(t1)
        team2_score = team_score(t2)
        match_score = min(team1_score, team2_score)  # A es 1 (más fuerte)

        cat = db.execute(sa.text("""
            SELECT id::text as id
            FROM categories
            WHERE ladder_code='MX' AND sort_order=:o
            LIMIT 1
        """), {"o": match_score}).mappings().first()
        if not cat:
            raise HTTPException(400, "Could not derive MX match category")
        return cat["id"]

    raise HTTPException(400, "Invalid ladder")

@router.post("", response_model=MatchOut)
def create_match(payload: MatchCreateIn, current=Depends(get_current_user), db: Session = Depends(get_db)):
    _assert_block_rules(db, current.id)

    if len(payload.participants) != 4:
        raise HTTPException(400, "Must include exactly 4 participants")

    try:
        participant_ids = [UUID(p.user_id) for p in payload.participants]
    except Exception:
        raise HTTPException(400, "Invalid participant user_id format")

    if len(set(participant_ids)) != 4:
        raise HTTPException(400, "Participants must be unique")

    t1 = [p for p in payload.participants if p.team_no == 1]
    t2 = [p for p in payload.participants if p.team_no == 2]
    if len(t1) != 2 or len(t2) != 2:
        raise HTTPException(400, "Each team must have 2 participants")

    if payload.club_id is not None:
        ok = db.execute(sa.text("SELECT 1 FROM clubs WHERE id=:c AND is_active=true"), {"c": payload.club_id}).first()
        if not ok:
            raise HTTPException(400, "Club not found or inactive")

    profiles = _fetch_profiles(db, participant_ids)
    ladder_code = _determine_ladder_from_genders([r["gender"] for r in profiles])

    _require_ladder_states(db, ladder_code, participant_ids)
    category_id = _derive_match_category_id(db, ladder_code, payload.participants, participant_ids)

    deadline = now_utc() + timedelta(hours=settings.CONFIRM_WINDOW_HOURS)

    match_id = db.execute(sa.text("""
        INSERT INTO matches (ladder_code, category_id, club_id, played_at, created_by, status, confirmation_deadline)
        VALUES (:ladder, :cat, :club, :played, :creator, 'pending_confirm', :dl)
        RETURNING id
    """), {
        "ladder": ladder_code,
        "cat": category_id,
        "club": payload.club_id,
        "played": payload.played_at,
        "creator": str(current.id),
        "dl": deadline,
    }).scalar_one()

    for p in payload.participants:
        db.execute(sa.text("""
            INSERT INTO match_participants (match_id, user_id, team_no)
            VALUES (:m, :u, :t)
        """), {"m": match_id, "u": p.user_id, "t": p.team_no})

    winner_team = payload.score.derived_winner()

    if payload.score.winner_team_no is not None and payload.score.winner_team_no != winner_team:
        raise HTTPException(400, "winner_team_no does not match derived winner from sets")

    db.execute(sa.text("""
        INSERT INTO match_scores (match_id, score_json, winner_team_no)
        VALUES (:m, CAST(:s AS jsonb), :w)
    """), {"m": match_id, "s": json.dumps(payload.score.score_json), "w": winner_team})


    for uid in participant_ids:
        db.execute(sa.text("""
            INSERT INTO match_confirmations (match_id, user_id, status)
            VALUES (:m, :u, 'pending')
        """), {"m": match_id, "u": str(uid)})

    audit(db, current.id, "match", str(match_id), "created", {
        "ladder_code": ladder_code,
        "category_id": category_id,
        "club_id": payload.club_id,
        "participants": [str(x) for x in participant_ids],
    })

    db.commit()

    row = db.execute(sa.text("""
        SELECT id::text as id, ladder_code, category_id::text as category_id, club_id::text as club_id,
               played_at, created_by::text as created_by, status, confirmation_deadline,
               confirmed_count, has_dispute
        FROM matches WHERE id=:m
    """), {"m": match_id}).mappings().first()
    return MatchOut(**row)

@router.get("/{match_id}", response_model=MatchOut)
def get_match(match_id: str, db: Session = Depends(get_db)):
    row = db.execute(sa.text("""
        SELECT id::text as id, ladder_code, category_id::text as category_id, club_id::text as club_id,
               played_at, created_by::text as created_by, status, confirmation_deadline,
               confirmed_count, has_dispute
        FROM matches WHERE id=:m
    """), {"m": match_id}).mappings().first()
    if not row:
        raise HTTPException(404, "Match not found")
    return MatchOut(**row)

def _apply_ranking_for_match(db: Session, match_id: str):
    m = db.execute(sa.text("""
        SELECT id::text as id, ladder_code, category_id::text as category_id, status, has_dispute, rank_processed_at
        FROM matches WHERE id=:m
        FOR UPDATE
    """), {"m": match_id}).mappings().first()
    if not m:
        return
    if m["rank_processed_at"] is not None:
        return
    if m["status"] != "verified" or m["has_dispute"]:
        return

    score_row = db.execute(sa.text("""
        SELECT score_json, winner_team_no
        FROM match_scores
        WHERE match_id=:m
    """), {"m": match_id}).mappings().first()

    if not score_row:
        return

    winner_team = int(score_row["winner_team_no"])
    score_json = score_row["score_json"]

    parts = db.execute(sa.text("""
        SELECT user_id::text as user_id, team_no
        FROM match_participants
        WHERE match_id=:m
        ORDER BY team_no
    """), {"m": match_id}).mappings().all()
    if len(parts) != 4:
        return

    team1_ids = [p["user_id"] for p in parts if p["team_no"] == 1]
    team2_ids = [p["user_id"] for p in parts if p["team_no"] == 2]
    all_ids = team1_ids + team2_ids

    states = db.execute(sa.text("""
        SELECT user_id::text as user_id, ladder_code, category_id::text as category_id, rating, verified_matches
        FROM user_ladder_state
        WHERE ladder_code=:l AND user_id = ANY(:ids)
        FOR UPDATE
    """), {"l": m["ladder_code"], "ids": all_ids}).mappings().all()

    if len(states) != 4:
        audit(db, None, "ranking", str(match_id), "skipped_missing_ladder_state", {"ladder": m["ladder_code"]})
        return

    st_by_user = {s["user_id"]: s for s in states}

    t1_rating = sum(int(st_by_user[uid]["rating"]) for uid in team1_ids) / 2.0
    t2_rating = sum(int(st_by_user[uid]["rating"]) for uid in team2_ids) / 2.0
    
    f = extract_score_features(score_json)
    mov_w = mov_weight_from_features(f)

    anti_farming_w = 1.0 
    weight_total = anti_farming_w * mov_w
    
    def k_for_vm(vm: int) -> int:
        if vm < 5:
            return 48
        if vm < 20:
            return 32
        return 24

    k_vals = [k_for_vm(int(st_by_user[uid]["verified_matches"])) for uid in all_ids]
    K_eff = int(round(sum(k_vals) / len(k_vals)))

    elo = compute_elo(t1_rating, t2_rating, winner_team_no=winner_team, k=K_eff, weight=weight_total)

    t1_delta = elo.delta_team1
    t2_delta = elo.delta_team2

    def cap_delta(uid: str, delta: int) -> int:
        vm = int(st_by_user[uid]["verified_matches"])
        if vm >= settings.PROVISIONAL_MATCHES:
            return delta
        cap = settings.PROVISIONAL_CAP
        return max(-cap, min(cap, delta))

    for uid in team1_ids:
        old = int(st_by_user[uid]["rating"])
        d = cap_delta(uid, t1_delta)
        new = old + d
        db.execute(sa.text("""
            UPDATE user_ladder_state
            SET rating=:r,
                verified_matches=verified_matches+1,
                is_provisional = (verified_matches+1) < :prov_n,
                updated_at=now()
            WHERE user_id=:u AND ladder_code=:l
        """), {"r": new, "u": uid, "l": m["ladder_code"], "prov_n": settings.PROVISIONAL_MATCHES})

        db.execute(sa.text("""
            INSERT INTO rating_events (match_id, ladder_code, category_id, user_id, old_rating, new_rating, delta, k_factor, weight)
            VALUES (:m, :l, :c, :u, :o, :n, :d, :k, :w)
        """), {"m": match_id, "l": m["ladder_code"], "c": m["category_id"], "u": uid, "o": old, "n": new, "d": d, "k": K_eff, "w": weight_total})

    for uid in team2_ids:
        old = int(st_by_user[uid]["rating"])
        d = cap_delta(uid, t2_delta)
        new = old + d
        db.execute(sa.text("""
            UPDATE user_ladder_state
            SET rating=:r,
                verified_matches=verified_matches+1,
                is_provisional = (verified_matches+1) < :prov_n,
                updated_at=now()
            WHERE user_id=:u AND ladder_code=:l
        """), {"r": new, "u": uid, "l": m["ladder_code"], "prov_n": settings.PROVISIONAL_MATCHES})

        db.execute(sa.text("""
            INSERT INTO rating_events (match_id, ladder_code, category_id, user_id, old_rating, new_rating, delta, k_factor, weight)
            VALUES (:m, :l, :c, :u, :o, :n, :d, :k, :w)
        """), {"m": match_id, "l": m["ladder_code"], "c": m["category_id"], "u": uid, "o": old, "n": new, "d": d, "k": K_eff, "w": weight_total})

    db.execute(sa.text("UPDATE matches SET rank_processed_at=now() WHERE id=:m"), {"m": match_id})
    
    audit(db, None, "ranking", str(match_id), "applied", {
        "k": K_eff,
        "winner_team": winner_team,
        "mov_w": round(mov_w, 3),
        "sets_played": f.sets_played,
        "games_margin": f.games_margin,
        "total_games": f.total_games,
    })

@router.get("/{match_id}/confirmations", response_model=MatchConfirmationsOut)
def match_confirmations(match_id: str, current=Depends(get_current_user), db: Session = Depends(get_db)):
    _assert_is_participant(db, match_id, str(current.id))

    m = db.execute(sa.text("""
        SELECT id::text as match_id, status, confirmation_deadline, confirmed_count, has_dispute
        FROM matches
        WHERE id=:m
    """), {"m": match_id}).mappings().first()
    if not m:
        raise HTTPException(404, "Match not found")

    rows = db.execute(sa.text("""
        SELECT
            mp.user_id::text as user_id,
            up.alias as alias,
            mp.team_no as team_no,
            COALESCE(mc.status, 'pending') as status,
            mc.decided_at as decided_at
        FROM match_participants mp
        JOIN user_profiles up ON up.user_id = mp.user_id
        LEFT JOIN match_confirmations mc
          ON mc.match_id = mp.match_id AND mc.user_id = mp.user_id
        WHERE mp.match_id=:m
        ORDER BY mp.team_no, up.alias
    """), {"m": match_id}).mappings().all()

    return MatchConfirmationsOut(
        match_id=m["match_id"],
        status=m["status"],
        confirmation_deadline=m["confirmation_deadline"],
        confirmed_count=m["confirmed_count"],
        has_dispute=m["has_dispute"],
        rows=[MatchConfirmationRowOut(**r) for r in rows],
    )

@router.get("/{match_id}/detail", response_model=MatchDetailOut)
def match_detail(match_id: str, current=Depends(get_current_user), db: Session = Depends(get_db)):
    _assert_is_participant(db, match_id, str(current.id))

    m = db.execute(sa.text("""
        SELECT
            m.id::text as id,
            m.ladder_code,
            m.category_id::text as category_id,
            c.code as category_code,
            m.club_id::text as club_id,
            cl.name as club_name,
            m.played_at,
            m.created_by::text as created_by,
            m.status,
            m.confirmation_deadline,
            m.confirmed_count,
            m.has_dispute
        FROM matches m
        JOIN categories c ON c.id = m.category_id
        LEFT JOIN clubs cl ON cl.id = m.club_id
        WHERE m.id=:m
    """), {"m": match_id}).mappings().first()
    if not m:
        raise HTTPException(404, "Match not found")

    parts = db.execute(sa.text("""
        SELECT
            mp.user_id::text as user_id,
            up.alias as alias,
            mp.team_no as team_no
        FROM match_participants mp
        JOIN user_profiles up ON up.user_id = mp.user_id
        WHERE mp.match_id=:m
        ORDER BY mp.team_no, up.alias
    """), {"m": match_id}).mappings().all()

    score = db.execute(sa.text("""
        SELECT score_json, winner_team_no
        FROM match_scores
        WHERE match_id=:m
    """), {"m": match_id}).mappings().first()
    if not score:
        raise HTTPException(500, "Match score missing")

    return MatchDetailOut(
        **m,
        participants=[MatchParticipantOut(**p) for p in parts],
        score=MatchScoreOut(score_json=score["score_json"], winner_team_no=int(score["winner_team_no"])),
    )

@router.post("/{match_id}/confirm")
def confirm_match(match_id: str, payload: ConfirmIn, current=Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.status not in ("confirmed", "disputed"):
        raise HTTPException(400, "status must be confirmed or disputed")

    is_part = db.execute(sa.text("""
        SELECT 1 FROM match_participants WHERE match_id=:m AND user_id=:u
    """), {"m": match_id, "u": str(current.id)}).first()
    if not is_part:
        raise HTTPException(403, "Not a participant")

    m = db.execute(sa.text("""
        SELECT status, confirmation_deadline, has_dispute
        FROM matches WHERE id=:m
    """), {"m": match_id}).mappings().first()
    if not m:
        raise HTTPException(404, "Match not found")

    if m["status"] in ("expired", "void"):
        raise HTTPException(400, "Match not confirmable")
    if now_utc() > m["confirmation_deadline"]:
        raise HTTPException(400, "Confirmation window expired")

    db.execute(sa.text("""
        UPDATE match_confirmations
        SET status=:s, decided_at=now(), note=:n, source=:src
        WHERE match_id=:m AND user_id=:u
    """), {"s": payload.status, "n": payload.note, "src": payload.source, "m": match_id, "u": str(current.id)})

    if payload.status == "disputed":
        db.execute(sa.text("UPDATE matches SET has_dispute=true, status='disputed' WHERE id=:m"), {"m": match_id})
        db.execute(sa.text("""
            INSERT INTO match_disputes (match_id, opened_by, reason_code, comment, status)
            VALUES (:m, :u, 'USER_DISPUTE', :c, 'open')
            ON CONFLICT (match_id) DO NOTHING
        """), {"m": match_id, "u": str(current.id), "c": payload.note})
        audit(db, current.id, "match", match_id, "disputed", {"note": payload.note})
        db.commit()
        return {"ok": True, "status": "disputed"}

    confirmed_count = db.execute(sa.text("""
        SELECT count(*) FROM match_confirmations WHERE match_id=:m AND status='confirmed'
    """), {"m": match_id}).scalar_one()

    db.execute(sa.text("UPDATE matches SET confirmed_count=:c WHERE id=:m"), {"c": confirmed_count, "m": match_id})
    audit(db, current.id, "confirmation", f"{match_id}:{current.id}", "confirmed", {})

    m2 = db.execute(sa.text("SELECT has_dispute FROM matches WHERE id=:m"), {"m": match_id}).mappings().first()
    if confirmed_count >= 3 and not m2["has_dispute"]:
        db.execute(sa.text("UPDATE matches SET status='verified' WHERE id=:m"), {"m": match_id})
        audit(db, None, "match", match_id, "verified", {"confirmed_count": confirmed_count})
        _apply_ranking_for_match(db, match_id)

    db.commit()
    return {"ok": True, "confirmed_count": confirmed_count}
