from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import now_utc, otp_hash, pii_hash, random_otp_code
from app.db.session import get_db
from app.schemas.me import (
    MeOut,
    ProfileOut,
    ProfileUpdateIn,
    LadderStateOut,
    PlayEligibilityOut,
    ContactChangeRequestIn,
    ContactChangeRequestOut,
    ContactChangeConfirmIn,
    ContactChangeConfirmOut,
)
from app.services.audit import audit

from app.schemas.match import MyMatchesOut, MyMatchRowOut

router = APIRouter()

def _normalize_phone(phone_e164: str | None, country_code: str | None, phone_number: str | None) -> str:
    if phone_e164:
        raw = phone_e164.strip()
        if not raw.startswith("+"):
            raw = "+" + raw
        digits = "".join(ch for ch in raw if ch.isdigit())
        if not digits:
            raise HTTPException(400, "Telefono invalido")
        return "+" + digits

    cc = (country_code or "").strip().replace("+", "")
    nsn = "".join(ch for ch in (phone_number or "").strip() if ch.isdigit())
    if not cc or not nsn:
        raise HTTPException(400, "country_code y phone_number son obligatorios")
    return f"+{cc}{nsn}"

def _normalize_email(email: str | None) -> str:
    raw = (email or "").strip().lower()
    if not raw or "@" not in raw or "." not in raw.split("@")[-1]:
        raise HTTPException(400, "Email invalido")
    return raw

def _resolve_contact(phone_e164: str | None, country_code: str | None, phone_number: str | None, email: str | None) -> tuple[str, str]:
    if email:
        return ("email", _normalize_email(email))
    return ("phone", _normalize_phone(phone_e164, country_code, phone_number))

def _identity_in_use_by_other(db: Session, user_id: str, contact_kind: str, contact_value: str) -> bool:
    row = db.execute(sa.text("""
        SELECT 1
        FROM auth_identities
        WHERE kind=:k AND value=:v AND user_id<>:u
        LIMIT 1
    """), {"k": contact_kind, "v": contact_value, "u": user_id}).first()
    return bool(row)

def _upsert_verified_identity(db: Session, user_id: str, contact_kind: str, contact_value: str):
    current = db.execute(sa.text("""
        SELECT id
        FROM auth_identities
        WHERE user_id=:u AND kind=:k
        FOR UPDATE
    """), {"u": user_id, "k": contact_kind}).mappings().first()
    if current:
        db.execute(sa.text("""
            UPDATE auth_identities
            SET value=:v, is_verified=true, verified_at=now()
            WHERE id=:id
        """), {"id": current["id"], "v": contact_value})
        return
    db.execute(sa.text("""
        INSERT INTO auth_identities (user_id, kind, value, is_verified, verified_at)
        VALUES (:u, :k, :v, true, now())
    """), {"u": user_id, "k": contact_kind, "v": contact_value})

def _sum_verified_matches(db: Session, user_id) -> int:
    return int(db.execute(sa.text("""
        SELECT COALESCE(SUM(verified_matches), 0)
        FROM user_ladder_state
        WHERE user_id=:u
    """), {"u": user_id}).scalar_one())

def _get_category_id_by_code(db: Session, ladder_code: str, code: str) -> str:
    row = db.execute(sa.text("""
        SELECT id::text as id
        FROM categories
        WHERE ladder_code=:l AND code=:c
    """), {"l": ladder_code, "c": code}).mappings().first()
    if not row:
        raise HTTPException(400, f"Codigo de categoria invalido '{code}' para ladder '{ladder_code}'")
    return row["id"]

def _get_mx_code_from_map(db: Session, gender: str, primary_code: str) -> str:
    row = db.execute(sa.text("""
        SELECT mx_code
        FROM mx_category_map
        WHERE gender=:g AND primary_code=:p
    """), {"g": gender, "p": primary_code}).mappings().first()
    if not row:
        raise HTTPException(400, "Falta mapeo MX para genero/categoria")
    return row["mx_code"]

def _count_user_matches(db: Session, user_id, ladder_code: str | None = None) -> int:
    if ladder_code is None:
        return int(db.execute(sa.text("""
            SELECT count(*)
            FROM match_participants
            WHERE user_id=:u
        """), {"u": user_id}).scalar_one())
    return int(db.execute(sa.text("""
        SELECT count(*)
        FROM match_participants mp
        JOIN matches m ON m.id = mp.match_id
        WHERE mp.user_id=:u AND m.ladder_code=:l
    """), {"u": user_id, "l": ladder_code}).scalar_one())

def _upsert_ladder_state(db: Session, user_id, ladder_code: str, category_id: str):
    existing = db.execute(sa.text("""
        SELECT verified_matches, category_id::text AS category_id
        FROM user_ladder_state
        WHERE user_id=:u AND ladder_code=:l
    """), {"u": user_id, "l": ladder_code}).mappings().first()

    if existing:
        vm = int(existing["verified_matches"])
        current_cat = existing["category_id"]

        # Idempotencia: si mandan la misma categoria, OK sin tocar nada
        if current_cat == str(category_id):
            return

        # Si ya hay verificados, NO se permite cambiar
        if vm > 0:
            raise HTTPException(400, f"No se puede cambiar la categoria para ladder {ladder_code} despues de partidos verificados")
        if _count_user_matches(db, user_id, ladder_code) > 0:
            raise HTTPException(400, f"No se puede cambiar la categoria para ladder {ladder_code} despues de cualquier participacion en partidos")

        # vm == 0: se permite correccion
        db.execute(sa.text("""
            UPDATE user_ladder_state
            SET category_id=:c, updated_at=now()
            WHERE user_id=:u AND ladder_code=:l
        """), {"u": user_id, "l": ladder_code, "c": category_id})
        return

    # No existe aun: crear
    db.execute(sa.text("""
        INSERT INTO user_ladder_state (user_id, ladder_code, category_id, rating, verified_matches, is_provisional, trust_score)
        VALUES (:u, :l, :c, 1000, 0, true, 100)
    """), {"u": user_id, "l": ladder_code, "c": category_id})

@router.get("", response_model=MeOut)
def me(current=Depends(get_current_user), db: Session = Depends(get_db)):
    prof = db.execute(sa.text("""
        SELECT alias, gender, is_public, country, city, handedness, preferred_side, birthdate, first_name, last_name
        FROM user_profiles
        WHERE user_id=:u
    """), {"u": current.id}).mappings().first()

    profile = ProfileOut(**prof) if prof else None
    return MeOut(
        id=str(current.id),
        phone_e164=current.phone_e164,
        email=current.email,
        status=current.status,
        profile=profile,
    )

@router.post("/contact-change/request", response_model=ContactChangeRequestOut)
def request_contact_change(payload: ContactChangeRequestIn, current=Depends(get_current_user), db: Session = Depends(get_db)):
    contact_kind, contact_value = _resolve_contact(
        payload.phone_e164,
        payload.country_code,
        payload.phone_number,
        payload.email,
    )

    if contact_kind == "phone":
        if current.phone_e164 == contact_value:
            raise HTTPException(400, "El telefono ya esta configurado")
        exists = db.execute(
            sa.text("SELECT 1 FROM users WHERE phone_e164=:v AND id<>:u"),
            {"v": contact_value, "u": current.id},
        ).first()
    else:
        if (current.email or "").lower() == contact_value:
            raise HTTPException(400, "El email ya esta configurado")
        exists = db.execute(
            sa.text("SELECT 1 FROM users WHERE lower(email)=lower(:v) AND id<>:u"),
            {"v": contact_value, "u": current.id},
        ).first()

    if exists or _identity_in_use_by_other(db, str(current.id), contact_kind, contact_value):
        raise HTTPException(409, "El contacto ya esta en uso")

    last_row = db.execute(sa.text("""
        SELECT created_at
        FROM user_contact_changes
        WHERE user_id=:u AND contact_kind=:k
        ORDER BY created_at DESC
        LIMIT 1
    """), {"u": current.id, "k": contact_kind}).mappings().first()
    if last_row:
        cooldown_until = last_row["created_at"] + timedelta(seconds=settings.OTP_REQUEST_COOLDOWN_SECONDS)
        if now_utc() < cooldown_until:
            raise HTTPException(429, "Debes esperar 2 minutos antes de solicitar un nuevo codigo.")

    code = random_otp_code()
    code_h = otp_hash(code)
    expires_at = now_utc() + timedelta(minutes=settings.OTP_TTL_MINUTES)

    db.execute(sa.text("""
        INSERT INTO user_contact_changes (user_id, contact_kind, new_contact_value, code_hash, expires_at, attempts)
        VALUES (:u, :k, :v, :h, :e, 0)
    """), {"u": current.id, "k": contact_kind, "v": contact_value, "h": code_h, "e": expires_at})

    audit(
        db,
        current.id,
        "user_contact",
        str(current.id),
        "change_requested",
        {"contact_kind": contact_kind, "contact_hash": pii_hash(contact_value, contact_kind)},
    )
    db.commit()

    out = ContactChangeRequestOut(ok=True, contact_kind=contact_kind)
    if settings.ENV == "dev":
        out.dev_code = code
    return out

@router.post("/contact-change/confirm", response_model=ContactChangeConfirmOut)
def confirm_contact_change(payload: ContactChangeConfirmIn, current=Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.execute(sa.text("""
        SELECT id, contact_kind, new_contact_value, code_hash, expires_at, attempts, consumed_at
        FROM user_contact_changes
        WHERE user_id=:u AND contact_kind=:k
        ORDER BY created_at DESC
        LIMIT 1
        FOR UPDATE
    """), {"u": current.id, "k": payload.contact_kind}).mappings().first()

    if not row:
        raise HTTPException(400, "Solicitud de cambio de contacto no encontrada")
    if row["consumed_at"] is not None:
        raise HTTPException(400, "Solicitud de cambio de contacto ya utilizada")
    if now_utc() > row["expires_at"]:
        raise HTTPException(400, "Solicitud de cambio de contacto expirada")
    if row["attempts"] >= 5:
        raise HTTPException(400, "Demasiados intentos")
    if otp_hash(payload.code) != row["code_hash"]:
        db.execute(sa.text("""
            UPDATE user_contact_changes
            SET attempts=attempts+1
            WHERE id=:id
        """), {"id": row["id"]})
        db.commit()
        raise HTTPException(400, "OTP invalido")

    if payload.contact_kind == "phone":
        exists = db.execute(sa.text("""
            SELECT 1
            FROM users
            WHERE phone_e164=:v AND id<>:u
        """), {"v": row["new_contact_value"], "u": current.id}).first()
        if exists or _identity_in_use_by_other(db, str(current.id), "phone", row["new_contact_value"]):
            raise HTTPException(409, "Telefono ya en uso")
        db.execute(sa.text("""
            UPDATE users
            SET phone_e164=:v
            WHERE id=:u
        """), {"v": row["new_contact_value"], "u": current.id})
        _upsert_verified_identity(db, str(current.id), "phone", row["new_contact_value"])
    else:
        exists = db.execute(sa.text("""
            SELECT 1
            FROM users
            WHERE lower(email)=lower(:v) AND id<>:u
        """), {"v": row["new_contact_value"], "u": current.id}).first()
        if exists or _identity_in_use_by_other(db, str(current.id), "email", row["new_contact_value"]):
            raise HTTPException(409, "Email ya en uso")
        db.execute(sa.text("""
            UPDATE users
            SET email=:v
            WHERE id=:u
        """), {"v": row["new_contact_value"], "u": current.id})
        _upsert_verified_identity(db, str(current.id), "email", row["new_contact_value"])

    db.execute(sa.text("""
        UPDATE user_contact_changes
        SET consumed_at=now()
        WHERE id=:id
    """), {"id": row["id"]})

    audit(
        db,
        current.id,
        "user_contact",
        str(current.id),
        "change_confirmed",
        {"contact_kind": payload.contact_kind},
    )
    db.commit()

    refreshed = db.execute(sa.text("""
        SELECT phone_e164, email
        FROM users
        WHERE id=:u
    """), {"u": current.id}).mappings().first()
    return ContactChangeConfirmOut(
        ok=True,
        contact_kind=payload.contact_kind,
        phone_e164=refreshed["phone_e164"],
        email=refreshed["email"],
    )

@router.get("/play-eligibility", response_model=PlayEligibilityOut)
def play_eligibility(current=Depends(get_current_user), db: Session = Depends(get_db)):
    prof = db.execute(sa.text("""
        SELECT alias, gender
        FROM user_profiles
        WHERE user_id=:u
    """), {"u": current.id}).mappings().first()

    if not prof:
        return PlayEligibilityOut(
            can_play=False,
            can_create_match=False,
            can_be_invited=False,
            missing=["perfil"],
            message="Debes completar tu perfil para poder jugar.",
        )

    missing: list[str] = []

    has_verified_contact = bool(db.execute(sa.text("""
        SELECT 1
        FROM auth_identities
        WHERE user_id=:u AND is_verified=true
        LIMIT 1
    """), {"u": current.id}).first())
    if not has_verified_contact:
        missing.append("canal_verificado")

    alias = prof.get("alias")
    gender = prof.get("gender")

    if alias is None or not alias.strip():
        missing.append("usuario")

    if gender not in ("M", "F"):
        missing.append("genero")

    preferred_ladder = {"M": "HM", "F": "WM"}.get(gender)
    ladders_to_check: list[str] = []
    if preferred_ladder:
        ladders_to_check.append(preferred_ladder)
        if preferred_ladder != "MX":
            ladders_to_check.append("MX")

    if ladders_to_check:
        rows = db.execute(sa.text("""
            SELECT ladder_code
            FROM user_ladder_state
            WHERE user_id=:u AND ladder_code = ANY(:ladders)
        """), {"u": str(current.id), "ladders": ladders_to_check}).mappings().all()
        have = {r["ladder_code"] for r in rows}
        if not any(ladder in have for ladder in ladders_to_check):
            missing.append("categoria")

    can_play = len(missing) == 0
    msg = None if can_play else "Completa tu perfil (canal verificado, usuario, genero y categoria) para crear o participar en partidos."

    return PlayEligibilityOut(
        can_play=can_play,
        can_create_match=can_play,
        can_be_invited=can_play,
        missing=missing,
        message=msg,
    )

@router.patch("/profile", response_model=MeOut)
def update_profile(payload: ProfileUpdateIn, current=Depends(get_current_user), db: Session = Depends(get_db)):
    # 1) leer perfil actual
    prof = db.execute(sa.text("""
        SELECT alias, gender, is_public, country, city, handedness, preferred_side, birthdate, first_name, last_name
        FROM user_profiles
        WHERE user_id=:u
    """), {"u": current.id}).mappings().first()
    if not prof:
        raise HTTPException(400, "Perfil no encontrado")

    # 2) alias unico si se cambia
    if payload.alias:
        exists = db.execute(sa.text("""
            SELECT 1
            FROM user_profiles
            WHERE lower(alias)=lower(:a) AND user_id<>:u
        """), {"a": payload.alias, "u": current.id}).first()
        if exists:
            raise HTTPException(400, "Alias ya en uso")

    # 3) gender valido
    if payload.gender is not None and payload.gender not in ("M", "F"):
        raise HTTPException(400, "El genero debe ser M o F")
    if payload.gender is not None and payload.gender != prof["gender"]:
        if _count_user_matches(db, current.id) > 0:
            raise HTTPException(400, "No se puede cambiar el genero despues de participar en partidos")
        if prof["gender"] in ("M", "F"):
            raise HTTPException(400, "El genero no se puede modificar una vez definido")

    # 4) update en user_profiles (solo lo que venga)
    updates = []
    params = {"u": current.id}

    if payload.alias is not None:
        updates.append("alias=:alias")
        params["alias"] = payload.alias

    if payload.gender is not None:
        updates.append("gender=:gender")
        params["gender"] = payload.gender

    if payload.is_public is not None:
        updates.append("is_public=:is_public")
        params["is_public"] = payload.is_public

    if payload.country is not None:
        country = payload.country.strip().upper()
        if len(country) != 2:
            raise HTTPException(400, "country debe ser ISO-2 (ej. CO)")
        updates.append("country=:country")
        params["country"] = country

    if payload.city is not None:
        city = payload.city.strip() if payload.city else None
        updates.append("city=:city")
        params["city"] = city

    if payload.handedness is not None:
        updates.append("handedness=:handedness")
        params["handedness"] = payload.handedness

    if payload.preferred_side is not None:
        updates.append("preferred_side=:preferred_side")
        params["preferred_side"] = payload.preferred_side

    if payload.birthdate is not None:
        updates.append("birthdate=:birthdate")
        params["birthdate"] = payload.birthdate

    if payload.first_name is not None:
        first_name = payload.first_name.strip() if payload.first_name else None
        updates.append("first_name=:first_name")
        params["first_name"] = first_name

    if payload.last_name is not None:
        last_name = payload.last_name.strip() if payload.last_name else None
        updates.append("last_name=:last_name")
        params["last_name"] = last_name

    if updates:
        db.execute(sa.text(f"""
            UPDATE user_profiles
            SET {', '.join(updates)}, updated_at=now()
            WHERE user_id=:u
        """), params)

    gender_eff = payload.gender if payload.gender is not None else prof["gender"]

    if payload.primary_category_code is not None and gender_eff not in ("M", "F"):
        raise HTTPException(400, "Debes definir tu genero (M o F) antes de elegir categoria.")
    
    if payload.primary_category_code is not None:
        primary_ladder = "HM" if gender_eff == "M" else "WM"

        primary_cat_id = _get_category_id_by_code(db, primary_ladder, payload.primary_category_code)
        _upsert_ladder_state(db, current.id, primary_ladder, primary_cat_id)

        mx_code = _get_mx_code_from_map(db, gender_eff, payload.primary_category_code)
        mx_cat_id = _get_category_id_by_code(db, "MX", mx_code)
        _upsert_ladder_state(db, current.id, "MX", mx_cat_id)

    audit(db, current.id, "profile", str(current.id), "updated", {
        "alias": payload.alias,
        "gender": payload.gender,
        "is_public": payload.is_public,
        "primary_category_code": payload.primary_category_code,
        "country": payload.country,
        "city": payload.city,
        "handedness": payload.handedness,
        "preferred_side": payload.preferred_side,
        "birthdate": str(payload.birthdate) if payload.birthdate else None,
        "first_name": payload.first_name,
        "last_name": payload.last_name,
    })

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        msg = str(getattr(exc, "orig", exc)).lower()
        if "alias" in msg or "uq_user_profiles_alias_lower" in msg or "user_profiles_alias_key" in msg:
            raise HTTPException(400, "Alias ya en uso")
        raise HTTPException(409, "Conflicto al actualizar perfil")
    return me(current=current, db=db)

@router.get("/ladder-states", response_model=list[LadderStateOut])
def my_ladder_states(current=Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(sa.text("""
        SELECT s.ladder_code,
               s.category_id::text as category_id,
               c.code as category_code,
               c.name as category_name,
               s.rating,
               s.verified_matches,
               s.is_provisional,
               s.trust_score
        FROM user_ladder_state s
        JOIN categories c ON c.id = s.category_id
        WHERE s.user_id=:u
        ORDER BY s.ladder_code
    """), {"u": current.id}).mappings().all()
    return [LadderStateOut(**r) for r in rows]

@router.get("/matches", response_model=MyMatchesOut)
def my_matches(
    ladder: str | None = Query(default=None, description="HM|WM|MX"),
    status: str | None = Query(default=None, description="pending_confirm|verified|disputed|expired|void"),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = sa.text("""
        SELECT
            m.id::text as id,
            m.ladder_code,
            c.code as category_code,
            m.club_id::text as club_id,
            cl.name as club_name,
            m.played_at,
            m.status,
            m.confirmation_deadline,
            m.confirmed_count,
            m.has_dispute,
            mp.team_no as my_team_no,
            COALESCE(mc.status, 'pending') as my_confirmation_status
        FROM matches m
        JOIN match_participants mp
        ON mp.match_id = m.id AND mp.user_id = :u
        JOIN categories c
        ON c.id = m.category_id
        LEFT JOIN clubs cl
        ON cl.id = m.club_id
        LEFT JOIN match_confirmations mc
        ON mc.match_id = m.id AND mc.user_id = :u
        WHERE (:ladder IS NULL OR m.ladder_code = :ladder)
        AND (:status IS NULL OR m.status = :status)
        ORDER BY m.played_at DESC, m.created_at DESC
        LIMIT :limit OFFSET :offset
    """).bindparams(
        sa.bindparam("ladder", type_=sa.String()),
        sa.bindparam("status", type_=sa.String()),
    )

    rows = db.execute(stmt, {
        "u": str(current.id),
        "ladder": ladder,
        "status": status,
        "limit": limit,
        "offset": offset
    }).mappings().all()

    out_rows = [MyMatchRowOut(**r) for r in rows]
    next_offset = (offset + limit) if len(out_rows) == limit else None
    return MyMatchesOut(rows=out_rows, limit=limit, offset=offset, next_offset=next_offset)



