from datetime import timedelta
from uuid import uuid4

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token_for_session,
    create_refresh_token_for_session,
    decode_token,
    hash_password,
    hash_refresh_token,
    now_utc,
    otp_hash,
    pii_hash,
    random_otp_code,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    LoginIn,
    LogoutIn,
    OTPRequestIn,
    OTPRequestOut,
    PasswordResetConfirmIn,
    PasswordResetRequestIn,
    RefreshIn,
    RegisterCompleteIn,
    SimpleOKOut,
    TokenOut,
)
from app.services.audit import audit

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


def _request_otp(db: Session, contact_kind: str, contact_value: str, purpose: str) -> OTPRequestOut:
    last_row = db.execute(sa.text("""
        SELECT created_at
        FROM auth_otps
        WHERE contact_kind=:k AND contact_value=:v AND purpose=:p
        ORDER BY created_at DESC
        LIMIT 1
    """), {"k": contact_kind, "v": contact_value, "p": purpose}).mappings().first()
    if last_row:
        cooldown_until = last_row["created_at"] + timedelta(seconds=settings.OTP_REQUEST_COOLDOWN_SECONDS)
        if now_utc() < cooldown_until:
            raise HTTPException(429, "Debes esperar 2 minutos antes de solicitar un nuevo codigo.")

    code = random_otp_code()
    db.execute(sa.text("""
        INSERT INTO auth_otps (phone_e164, contact_kind, contact_value, purpose, code_hash, expires_at, attempts)
        VALUES (:legacy_phone, :k, :v, :p, :h, :e, 0)
    """), {
        "legacy_phone": contact_value,
        "k": contact_kind,
        "v": contact_value,
        "p": purpose,
        "h": otp_hash(code),
        "e": now_utc() + timedelta(minutes=settings.OTP_TTL_MINUTES),
    })
    audit(
        db,
        None,
        "auth",
        f"{contact_kind}_sha256:{pii_hash(contact_value, contact_kind)}",
        "otp_requested",
        {"purpose": purpose},
    )
    out = OTPRequestOut(ok=True, purpose=purpose)
    if settings.ENV == "dev":
        out.dev_code = code
    return out


def _consume_otp(db: Session, contact_kind: str, contact_value: str, purpose: str, code: str):
    row = db.execute(sa.text("""
        SELECT id, code_hash, expires_at, attempts, consumed_at
        FROM auth_otps
        WHERE contact_kind=:k AND contact_value=:v AND purpose=:p
        ORDER BY created_at DESC
        LIMIT 1
        FOR UPDATE
    """), {"k": contact_kind, "v": contact_value, "p": purpose}).mappings().first()
    if not row:
        raise HTTPException(400, "OTP no encontrado")
    if row["consumed_at"] is not None:
        raise HTTPException(400, "OTP ya utilizado")
    if now_utc() > row["expires_at"]:
        raise HTTPException(400, "OTP expirado")
    if row["attempts"] >= 5:
        raise HTTPException(400, "Demasiados intentos")
    if otp_hash(code) != row["code_hash"]:
        db.execute(sa.text("UPDATE auth_otps SET attempts=attempts+1 WHERE id=:id"), {"id": row["id"]})
        db.commit()
        raise HTTPException(400, "OTP invalido")
    db.execute(sa.text("UPDATE auth_otps SET consumed_at=now() WHERE id=:id"), {"id": row["id"]})


def _get_identity(db: Session, contact_kind: str, contact_value: str):
    return db.execute(sa.text("""
        SELECT id, user_id::text AS user_id, is_verified
        FROM auth_identities
        WHERE kind=:k AND value=:v
    """), {"k": contact_kind, "v": contact_value}).mappings().first()


def _create_session_tokens(db: Session, user_id: str) -> TokenOut:
    sid = str(uuid4())
    refresh_token = create_refresh_token_for_session(user_id, sid=sid)
    refresh_hash = hash_refresh_token(refresh_token)
    expires_at = now_utc() + timedelta(days=settings.JWT_REFRESH_DAYS)

    db.execute(sa.text("""
        INSERT INTO auth_sessions (id, user_id, refresh_hash, expires_at)
        VALUES (:sid, :u, :h, :e)
    """), {"sid": sid, "u": user_id, "h": refresh_hash, "e": expires_at})

    access_token = create_access_token_for_session(user_id, sid=sid)
    return TokenOut(access_token=access_token, refresh_token=refresh_token)


def _parse_identifier(identifier: str) -> tuple[str, str]:
    value = identifier.strip()
    if "@" in value:
        return ("email", _normalize_email(value))
    return ("phone", _normalize_phone(value, None, None))


def _check_login_rate_limit(db: Session, login_key_hash: str):
    failed = int(db.execute(sa.text("""
        SELECT count(*)
        FROM auth_login_attempts
        WHERE login_key_hash=:k
          AND success=false
          AND created_at >= (now() - interval '15 minutes')
    """), {"k": login_key_hash}).scalar_one())
    if failed >= 8:
        raise HTTPException(429, "Demasiados intentos de inicio de sesion, intenta mas tarde")


def _record_login_attempt(db: Session, login_key_hash: str, success: bool):
    db.execute(sa.text("""
        INSERT INTO auth_login_attempts (login_key_hash, success)
        VALUES (:k, :s)
    """), {"k": login_key_hash, "s": success})


@router.post("/otp/request", response_model=OTPRequestOut)
def otp_request(payload: OTPRequestIn, db: Session = Depends(get_db)):
    contact_kind, contact_value = _resolve_contact(
        payload.phone_e164, payload.country_code, payload.phone_number, payload.email
    )

    if payload.purpose == "password_reset":
        ident = _get_identity(db, contact_kind, contact_value)
        if not ident or not ident["is_verified"]:
            # Evita enumerar cuentas en el flujo de reseteo.
            return OTPRequestOut(ok=True, purpose=payload.purpose)

    out = _request_otp(db, contact_kind, contact_value, payload.purpose)
    db.commit()
    return out


@router.post("/register/complete", response_model=TokenOut)
def register_complete(payload: RegisterCompleteIn, db: Session = Depends(get_db)):
    contact_kind, contact_value = _resolve_contact(
        payload.phone_e164, payload.country_code, payload.phone_number, payload.email
    )
    _consume_otp(db, contact_kind, contact_value, "register", payload.code)

    ident = _get_identity(db, contact_kind, contact_value)
    if ident:
        user_id = ident["user_id"]
        cred = db.execute(sa.text("""
            SELECT 1 FROM auth_credentials WHERE user_id=:u
        """), {"u": user_id}).first()
        if cred:
            raise HTTPException(409, "La cuenta ya esta registrada. Usa login.")
        db.execute(sa.text("""
            UPDATE auth_identities
            SET is_verified=true, verified_at=now()
            WHERE id=:id
        """), {"id": ident["id"]})
    else:
        if contact_kind == "phone":
            user_id = str(db.execute(sa.text("""
                INSERT INTO users (phone_e164, email, status)
                VALUES (:v, NULL, 'active')
                RETURNING id
            """), {"v": contact_value}).scalar_one())
        else:
            user_id = str(db.execute(sa.text("""
                INSERT INTO users (phone_e164, email, status)
                VALUES (NULL, :v, 'active')
                RETURNING id
            """), {"v": contact_value}).scalar_one())
        db.execute(sa.text("""
            INSERT INTO auth_identities (user_id, kind, value, is_verified, verified_at)
            VALUES (:u, :k, :v, true, now())
        """), {"u": user_id, "k": contact_kind, "v": contact_value})

    # Mantiene campos espejo en users para lecturas de aplicacion.
    if contact_kind == "phone":
        db.execute(sa.text("""
            UPDATE users
            SET phone_e164=COALESCE(phone_e164, :v)
            WHERE id=:u
        """), {"u": user_id, "v": contact_value})
    else:
        db.execute(sa.text("""
            UPDATE users
            SET email=COALESCE(email, :v)
            WHERE id=:u
        """), {"u": user_id, "v": contact_value})

    db.execute(sa.text("""
        INSERT INTO auth_credentials (user_id, password_hash, password_updated_at)
        VALUES (:u, :h, now())
    """), {"u": user_id, "h": hash_password(payload.password)})

    exists_profile = db.execute(sa.text("""
        SELECT 1 FROM user_profiles WHERE user_id=:u
    """), {"u": user_id}).first()
    if not exists_profile:
        suffix = (contact_value.split("@")[0][:4] if contact_kind == "email" else contact_value[-4:])
        base_alias = f"player_{suffix}"
        inserted = False
        for attempt in range(20):
            alias = base_alias if attempt == 0 else f"{base_alias}_{uuid4().hex[:6]}"
            row = db.execute(sa.text("""
                INSERT INTO user_profiles (user_id, alias, gender, is_public)
                VALUES (:u, :a, 'U', true)
                ON CONFLICT DO NOTHING
                RETURNING 1
            """), {"u": user_id, "a": alias}).first()
            if row:
                inserted = True
                break
        if not inserted:
            raise HTTPException(409, "No se pudo asignar un alias de perfil")

    tokens = _create_session_tokens(db, user_id)
    audit(db, user_id, "auth", str(user_id), "register_completed", {"contact_kind": contact_kind})
    db.commit()
    return tokens


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    kind, value = _parse_identifier(payload.identifier)
    login_key_hash = pii_hash(f"{kind}:{value}", "login")
    _check_login_rate_limit(db, login_key_hash)

    ident = _get_identity(db, kind, value)
    if not ident or not ident["is_verified"]:
        _record_login_attempt(db, login_key_hash, False)
        db.commit()
        raise HTTPException(401, "Credenciales invalidas")

    cred = db.execute(sa.text("""
        SELECT password_hash
        FROM auth_credentials
        WHERE user_id=:u
    """), {"u": ident["user_id"]}).mappings().first()
    if not cred or not verify_password(payload.password, cred["password_hash"]):
        _record_login_attempt(db, login_key_hash, False)
        db.commit()
        raise HTTPException(401, "Credenciales invalidas")

    user = db.get(User, ident["user_id"])
    if not user:
        raise HTTPException(401, "Usuario no encontrado")
    if user.status != "active":
        raise HTTPException(403, "Usuario bloqueado")

    _record_login_attempt(db, login_key_hash, True)
    db.execute(sa.text("UPDATE users SET last_login_at=now() WHERE id=:u"), {"u": ident["user_id"]})
    tokens = _create_session_tokens(db, str(ident["user_id"]))
    audit(db, ident["user_id"], "auth", str(ident["user_id"]), "login", {})
    db.commit()
    return tokens


@router.post("/password-reset/request", response_model=OTPRequestOut)
def password_reset_request(payload: PasswordResetRequestIn, db: Session = Depends(get_db)):
    contact_kind, contact_value = _resolve_contact(
        payload.phone_e164, payload.country_code, payload.phone_number, payload.email
    )
    ident = _get_identity(db, contact_kind, contact_value)
    if not ident or not ident["is_verified"]:
        return OTPRequestOut(ok=True, purpose="password_reset")
    out = _request_otp(db, contact_kind, contact_value, "password_reset")
    db.commit()
    return out


@router.post("/password-reset/confirm", response_model=SimpleOKOut)
def password_reset_confirm(payload: PasswordResetConfirmIn, db: Session = Depends(get_db)):
    contact_kind, contact_value = _resolve_contact(
        payload.phone_e164, payload.country_code, payload.phone_number, payload.email
    )
    _consume_otp(db, contact_kind, contact_value, "password_reset", payload.code)
    ident = _get_identity(db, contact_kind, contact_value)
    if not ident:
        raise HTTPException(400, "Identidad no encontrada")

    exists = db.execute(sa.text("""
        SELECT 1 FROM auth_credentials WHERE user_id=:u
    """), {"u": ident["user_id"]}).first()
    if exists:
        db.execute(sa.text("""
            UPDATE auth_credentials
            SET password_hash=:h, password_updated_at=now()
            WHERE user_id=:u
        """), {"u": ident["user_id"], "h": hash_password(payload.new_password)})
    else:
        db.execute(sa.text("""
            INSERT INTO auth_credentials (user_id, password_hash, password_updated_at)
            VALUES (:u, :h, now())
        """), {"u": ident["user_id"], "h": hash_password(payload.new_password)})

    db.execute(sa.text("""
        UPDATE auth_sessions
        SET revoked_at=now(), revoked_reason='password_reset'
        WHERE user_id=:u AND revoked_at IS NULL
    """), {"u": ident["user_id"]})

    audit(db, ident["user_id"], "auth", str(ident["user_id"]), "password_reset", {})
    db.commit()
    return SimpleOKOut(ok=True)


@router.post("/refresh", response_model=TokenOut)
def refresh(payload: RefreshIn, db: Session = Depends(get_db)):
    try:
        decoded = decode_token(payload.refresh_token)
    except Exception:
        raise HTTPException(401, "Refresh token invalido")
    if decoded.get("type") != "refresh":
        raise HTTPException(401, "Tipo de token invalido")

    user_id = decoded.get("sub")
    sid = decoded.get("sid")
    if not sid:
        raise HTTPException(401, "Refresh token invalido")

    row = db.execute(sa.text("""
        SELECT id, user_id::text AS user_id, refresh_hash, expires_at, revoked_at
        FROM auth_sessions
        WHERE id=:sid
        FOR UPDATE
    """), {"sid": sid}).mappings().first()
    if not row or row["user_id"] != str(user_id):
        raise HTTPException(401, "Sesion no encontrada")
    if row["revoked_at"] is not None:
        raise HTTPException(401, "Sesion revocada")
    if now_utc() > row["expires_at"]:
        raise HTTPException(401, "Sesion expirada")
    if row["refresh_hash"] != hash_refresh_token(payload.refresh_token):
        raise HTTPException(401, "Refresh token invalido")

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(401, "Usuario no encontrado")
    if user.status != "active":
        raise HTTPException(403, "Usuario bloqueado")

    new_tokens = _create_session_tokens(db, str(user_id))
    new_payload = decode_token(new_tokens.refresh_token)
    new_sid = new_payload.get("sid")

    db.execute(sa.text("""
        UPDATE auth_sessions
        SET revoked_at=now(), revoked_reason='rotated', replaced_by=:new_sid
        WHERE id=:sid
    """), {"sid": sid, "new_sid": new_sid})
    db.commit()
    return new_tokens


@router.post("/logout", response_model=SimpleOKOut)
def logout(payload: LogoutIn, db: Session = Depends(get_db)):
    try:
        decoded = decode_token(payload.refresh_token)
    except Exception:
        return SimpleOKOut(ok=True)
    sid = decoded.get("sid")
    if sid:
        row = db.execute(sa.text("""
            SELECT refresh_hash
            FROM auth_sessions
            WHERE id=:sid
            FOR UPDATE
        """), {"sid": sid}).mappings().first()
        if row and row["refresh_hash"] == hash_refresh_token(payload.refresh_token):
            db.execute(sa.text("""
                UPDATE auth_sessions
                SET revoked_at=now(), revoked_reason='logout'
                WHERE id=:sid
            """), {"sid": sid})
            db.commit()
    return SimpleOKOut(ok=True)
