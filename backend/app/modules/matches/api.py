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
    MatchCreateIn, MatchOut, ConfirmIn, ConfirmOut, MatchScoreIn,
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
    uid = str(user_id)

    pending = db.execute(sa.text("""
        SELECT count(*)
        FROM matches
        WHERE created_by=:u
          AND status='pending_confirm'
          AND confirmation_deadline >= now()
    """), {"u": uid}).scalar_one()

    expired_effective = db.execute(sa.text("""
        SELECT count(*)
        FROM matches
        WHERE created_by=:u
          AND status='pending_confirm'
          AND confirmation_deadline < now()
          AND created_at >= (now() - interval '30 days')
    """), {"u": uid}).scalar_one()

    expired_materialized = db.execute(sa.text("""
        SELECT count(*)
        FROM matches
        WHERE created_by=:u
          AND status='expired'
          AND created_at >= (now() - interval '30 days')
    """), {"u": uid}).scalar_one()

    expired = int(expired_effective) + int(expired_materialized)

    if pending >= 2 or expired >= 1:
        raise HTTPException(403, "Blocked from creating new match (pending/expired limit)")

def _fetch_profiles(db: Session, user_ids: list[UUID]):
    ids_bp = sa.bindparam("ids", expanding=True)

    rows = db.execute(
        sa.text("""
            SELECT
                user_id::text AS user_id,
                alias,
                gender
            FROM user_profiles
            WHERE user_id::text IN :ids
        """).bindparams(ids_bp),
        {"ids": [str(x) for x in user_ids]},
    ).mappings().all()

    return [dict(r) for r in rows]

def _determine_ladder_from_genders(genders: list[str]) -> str:
    m = genders.count("M")
    f = genders.count("F")
    if m == 4 and f == 0:
        return "HM"
    if f == 4 and m == 0:
        return "WM"
    if m == 2 and f == 2:
        return "MX"
    raise HTTPException(400, "CombinaciÃ³n de gÃ©neros no vÃ¡lida. Utilice 4M (HM), 4F (WM) o 2M2F (MX).")

def _derive_match_category_id(db: Session, ladder_code: str, participant_ids: list[UUID]) -> str:
    """
    C3.1: category_id del match = categorÃ­a mediana de los 4 participantes (por sort_order)
    en el ladder del match (HM/WM/MX). Solo etiqueta para analÃ­tica.
    """
    rows = db.execute(sa.text("""
        SELECT c.sort_order
        FROM user_ladder_state s
        JOIN categories c ON c.id = s.category_id
        WHERE s.ladder_code = :l
          AND s.user_id = ANY(:ids)
    """), {"l": ladder_code, "ids": participant_ids}).mappings().all()

    if len(rows) != 4:
        raise HTTPException(400, "Falta el estado/categorÃ­a de la tabla para los participantes.")

    sort_orders = sorted(int(r["sort_order"]) for r in rows)

    median_val = (sort_orders[1] + sort_orders[2]) / 2.0

    target = int(math.ceil(median_val))
    cats = db.execute(sa.text("""
        SELECT id::text as id, sort_order
        FROM categories
        WHERE ladder_code = :l
    """), {"l": ladder_code}).mappings().all()

    if not cats:
        raise HTTPException(400, "No hay categorÃ­as para la tabla")

    best = min(
        cats,
        key=lambda c: (abs(int(c["sort_order"]) - target), int(c["sort_order"]))
    )
    return best["id"]

@router.post("", response_model=MatchOut)
def create_match(payload: MatchCreateIn, current=Depends(get_current_user), db: Session = Depends(get_db)):
    _assert_block_rules(db, current.id)

    if len(payload.participants) != 4:
        raise HTTPException(400, "Debe incluir exactamente 4 participantes")

    try:
        participant_ids = [UUID(p.user_id) for p in payload.participants]
    except Exception:
        raise HTTPException(400, "Formato de ID de participante invÃ¡lido")

    if len(set(participant_ids)) != 4:
        raise HTTPException(400, "Los participantes deben ser unicos.")
    if UUID(str(current.id)) not in participant_ids:
        raise HTTPException(403, "El creador del partido debe estar entre los 4 participantes.")
    t1 = [p for p in payload.participants if p.team_no == 1]
    t2 = [p for p in payload.participants if p.team_no == 2]
    if len(t1) != 2 or len(t2) != 2:
        raise HTTPException(400, "Cada equipo debe tener 2 participantes")

    if payload.club_id is not None:
        ok = db.execute(sa.text("SELECT 1 FROM clubs WHERE id=:c AND is_active=true"), {"c": payload.club_id}).first()
        if not ok:
            raise HTTPException(400, "Club no encontrado o inactivo")

    profiles = _fetch_profiles(db, participant_ids)
    profiles_by_id = {UUID(p["user_id"]): p for p in profiles if p.get("user_id")}

    missing_profiles = [uid for uid in participant_ids if uid not in profiles_by_id]
    if missing_profiles:
        raise HTTPException(
            status_code=403,
            detail="No se puede crear/invitar a partidos: todos los jugadores deben tener perfil creado."
        )

    bad = set()
    ids_bp = sa.bindparam("ids", expanding=True)

    verified_rows = db.execute(
        sa.text("""
            SELECT user_id::text AS user_id
            FROM auth_identities
            WHERE is_verified=true
              AND user_id::text IN :ids
            GROUP BY user_id
        """).bindparams(ids_bp),
        {"ids": [str(x) for x in participant_ids]},
    ).mappings().all()
    verified_users = {UUID(r["user_id"]) for r in verified_rows}
    if any(uid not in verified_users for uid in participant_ids):
        bad.add("canal_verificado")

    for uid in participant_ids:
        p = profiles_by_id[uid]
        alias = p.get("alias")
        if alias is None or not alias.strip():
            bad.add("usuario")
        if p.get("gender") not in ("M", "F"):
            bad.add("genero")

    if "genero" in bad:
        raise HTTPException(
            status_code=403,
            detail="No se puede crear/invitar a partidos: todos los jugadores deben completar su perfil minimo (canal verificado, usuario, genero y categoria)."
        )

    ladder_code = _determine_ladder_from_genders([profiles_by_id[uid]["gender"] for uid in participant_ids])

    rows = db.execute(
        sa.text("""
            SELECT user_id::text AS user_id
            FROM user_ladder_state
            WHERE ladder_code = :ladder
            AND user_id::text IN :ids
        """).bindparams(ids_bp),
        {"ladder": ladder_code, "ids": [str(x) for x in participant_ids]},
    ).mappings().all()

    has_state = {UUID(r["user_id"]) for r in rows}
    missing_category = [uid for uid in participant_ids if uid not in has_state]
    if missing_category:
        bad.add("categoria")

    if bad:
        raise HTTPException(
            status_code=403,
            detail="No se puede crear/invitar a partidos: todos los jugadores deben completar su perfil minimo (canal verificado, usuario, genero y categoria)."
        )

    category_id = _derive_match_category_id(db, ladder_code, participant_ids)

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
        raise HTTPException(400, "Equipo ganador no coincide con el ganador derivado de los conjuntos")

    db.execute(sa.text("""
        INSERT INTO match_scores (match_id, score_json, winner_team_no)
        VALUES (:m, CAST(:s AS jsonb), :w)
    """), {"m": match_id, "s": json.dumps(payload.score.score_json), "w": winner_team})

    creator_id = str(current.id)

    for uid in participant_ids:
        uid_str = str(uid)
        if uid_str == creator_id:
            db.execute(sa.text("""
                INSERT INTO match_confirmations (match_id, user_id, status, decided_at, source)
                VALUES (:m, :u, 'confirmed', now(), 'creator')
            """), {"m": match_id, "u": uid_str})
        else:
            db.execute(sa.text("""
                INSERT INTO match_confirmations (match_id, user_id, status)
                VALUES (:m, :u, 'pending')
            """), {"m": match_id, "u": uid_str})

    db.execute(sa.text("""
        UPDATE matches
        SET confirmed_count=:c
        WHERE id=:m
    """), {"c": 1, "m": match_id})

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
def get_match(match_id: str, current=Depends(get_current_user), db: Session = Depends(get_db)):
    _assert_is_participant(db, match_id, str(current.id))

    row = db.execute(sa.text("""
        SELECT
            id::text as id,
            ladder_code,
            category_id::text as category_id,
            club_id::text as club_id,
            played_at,
            created_by::text as created_by,
            CASE
                WHEN status='pending_confirm' AND confirmation_deadline < now()
                    THEN 'expired'
                ELSE status
            END as status,
            confirmation_deadline,
            confirmed_count,
            has_dispute
        FROM matches
        WHERE id=:m
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
        SELECT
            id::text as match_id,
            CASE
                WHEN status='pending_confirm' AND confirmation_deadline < now()
                    THEN 'expired'
                ELSE status
            END as status,
            confirmation_deadline,
            has_dispute
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

    confirmed_count = sum(1 for r in rows if r["status"] == "confirmed")

    return MatchConfirmationsOut(
        match_id=m["match_id"],
        status=m["status"], 
        confirmation_deadline=m["confirmation_deadline"],
        confirmed_count=int(confirmed_count),
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
    
    if m["status"] == "pending_confirm" and m["confirmation_deadline"] < now_utc():
        db.execute(sa.text("""
            UPDATE matches
            SET status='expired'
            WHERE id=:m AND status='pending_confirm'
        """), {"m": match_id})
        
        db.commit()
        
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
        SELECT
        COALESCE(m.proposed_score_json::jsonb, ms.score_json::jsonb) AS score_json,
        COALESCE(m.proposed_winner_team_no, ms.winner_team_no)       AS winner_team_no
        FROM matches m
        JOIN match_scores ms ON ms.match_id = m.id
        WHERE m.id=:m
    """), {"m": match_id}).mappings().first()

    if not score:
        raise HTTPException(500, "Falta el resultado del partido.")

    return MatchDetailOut(
        **m,
        participants=[MatchParticipantOut(**p) for p in parts],
        score=MatchScoreOut(score_json=score["score_json"], winner_team_no=int(score["winner_team_no"])),
    )

@router.post("/{match_id}/confirm", response_model=ConfirmOut)
def confirm_match(match_id: str, payload: ConfirmIn, current=Depends(get_current_user), db: Session = Depends(get_db)):
    _assert_is_participant(db, match_id, str(current.id))

    m = db.execute(sa.text("""
        SELECT
            id::text as match_id,
            status,
            confirmation_deadline,
            proposal_count,
            proposed_score_json,
            proposed_winner_team_no
        FROM matches
        WHERE id=:m
        FOR UPDATE
    """), {"m": match_id}).mappings().first()

    if not m:
        raise HTTPException(404, "Partido no encontrado")

    if m["status"] == "pending_confirm" and m["confirmation_deadline"] < now_utc():
        db.execute(sa.text("""
            UPDATE matches
            SET status='expired'
            WHERE id=:m AND status='pending_confirm'
        """), {"m": match_id})
        db.commit()
        raise HTTPException(409, "Patido expirado")

    if m["status"] != "pending_confirm":
        raise HTTPException(
            status_code=409,
            detail=f"El partido no estÃ¡ pendiente de confirmaciÃ³n (estado={m['status']})."
        )


    active = db.execute(sa.text("""
        SELECT
        COALESCE(m.proposed_score_json::jsonb, ms.score_json::jsonb) AS score_json
        FROM matches m
        JOIN match_scores ms ON ms.match_id = m.id
        WHERE m.id=:m
    """), {"m": match_id}).mappings().first()

    active_score_json = active["score_json"]

    if payload.score_json is not None and payload.score_json != active_score_json:
        if int(m["proposal_count"] or 0) >= settings.MAX_SCORE_PROPOSALS:
            raise HTTPException(
                status_code=409,
                detail="LÃ­mite de apelaciones alcanzado (mÃ¡ximo 2)."
            )

        score_in = MatchScoreIn(score_json=payload.score_json)
        winner_team_no = int(score_in.derived_winner())

        db.execute(sa.text("""
            UPDATE matches
            SET
              proposed_score_json = CAST(:s AS jsonb),
              proposed_winner_team_no = :w,
              proposed_by = :u,
              proposed_at = now(),
              proposal_count = proposal_count + 1
            WHERE id=:m
        """), {
            "m": match_id,
            "s": json.dumps(payload.score_json),
            "w": winner_team_no,
            "u": str(current.id),
        })

        db.execute(sa.text("""
            UPDATE match_confirmations
            SET status='pending', decided_at=NULL, note=NULL, source=NULL
            WHERE match_id=:m
        """), {"m": match_id})

        db.execute(sa.text("""
            UPDATE match_confirmations
            SET status='confirmed', decided_at=now(), note=:note, source=:source
            WHERE match_id=:m AND user_id=:u
        """), {
            "m": match_id,
            "u": str(current.id),
            "note": payload.note,
            "source": payload.source,
        })

        db.execute(sa.text("""
            UPDATE matches
            SET confirmed_count=1
            WHERE id=:m
        """), {"m": match_id})

        db.commit()
        return ConfirmOut(ok=True, confirmed_count=1, teams_confirmed=1)

    db.execute(sa.text("""
        UPDATE match_confirmations
        SET status='confirmed', decided_at=now(), note=:note, source=:source
        WHERE match_id=:m AND user_id=:u
    """), {"m": match_id, "u": str(current.id), "note": payload.note, "source": payload.source})

    confirmed_count = db.execute(sa.text("""
        SELECT count(*)::int as c
        FROM match_confirmations
        WHERE match_id=:m AND status='confirmed'
    """), {"m": match_id}).mappings().first()["c"]

    teams_confirmed = db.execute(sa.text("""
        SELECT count(distinct mp.team_no)::int as c
        FROM match_confirmations mc
        JOIN match_participants mp ON mp.match_id=mc.match_id AND mp.user_id=mc.user_id
        WHERE mc.match_id=:m AND mc.status='confirmed'
    """), {"m": match_id}).mappings().first()["c"]

    db.execute(sa.text("""
        UPDATE matches
        SET confirmed_count=:c
        WHERE id=:m
    """), {"m": match_id, "c": confirmed_count})

    if teams_confirmed >= 2:
        prop = db.execute(sa.text("""
            SELECT proposed_score_json, proposed_winner_team_no
            FROM matches
            WHERE id=:m
        """), {"m": match_id}).mappings().first()

        if prop and prop["proposed_score_json"] is not None:
            db.execute(sa.text("""
                UPDATE match_scores
                SET score_json=CAST(:s AS jsonb), winner_team_no=:w
                WHERE match_id=:m
            """), {"m": match_id, "s": json.dumps(prop["proposed_score_json"]), "w": int(prop["proposed_winner_team_no"])})

            db.execute(sa.text("""
                UPDATE matches
                SET proposed_score_json=NULL,
                    proposed_winner_team_no=NULL,
                    proposed_by=NULL,
                    proposed_at=NULL
                WHERE id=:m
            """), {"m": match_id})

        db.execute(sa.text("""
            UPDATE matches
            SET status='verified'
            WHERE id=:m
        """), {"m": match_id})

        _apply_ranking_for_match(db, match_id)

    db.commit()
    return ConfirmOut(ok=True, confirmed_count=confirmed_count, teams_confirmed=teams_confirmed)


