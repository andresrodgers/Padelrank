from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import sqlalchemy as sa

from app.core.config import settings
from app.core.security import random_otp_code, otp_hash, create_access_token, create_refresh_token, decode_token
from app.db.session import get_db
from app.models.user import User
from app.models.profile import UserProfile
from app.schemas.auth import OTPRequestIn, OTPRequestOut, OTPVerifyIn, TokenOut, RefreshIn
from app.services.audit import audit
from app.core.security import now_utc

router = APIRouter()

# Simple OTP table lives as raw SQL in migration? We'll model it inline via SQLAlchemy Table to keep P0 small.
# We'll access it via SQLAlchemy text queries.

@router.post("/otp/request", response_model=OTPRequestOut)
def otp_request(payload: OTPRequestIn, db: Session = Depends(get_db)):
    code = random_otp_code()
    expires_at = now_utc() + timedelta(minutes=settings.OTP_TTL_MINUTES)
    code_h = otp_hash(code)

    db.execute(sa.text("""
        INSERT INTO auth_otps (phone_e164, code_hash, expires_at, attempts)
        VALUES (:p, :h, :e, 0)
    """), {"p": payload.phone_e164, "h": code_h, "e": expires_at})
    audit(db, None, "auth", payload.phone_e164, "otp_requested", {"expires_at": expires_at.isoformat()})
    db.commit()

    out = OTPRequestOut(ok=True)
    if settings.ENV == "dev":
        out.dev_code = code
    return out

@router.post("/otp/verify", response_model=TokenOut)
def otp_verify(payload: OTPVerifyIn, db: Session = Depends(get_db)):
    row = db.execute(sa.text("""
        SELECT id, code_hash, expires_at, attempts, consumed_at
        FROM auth_otps
        WHERE phone_e164=:p
        ORDER BY created_at DESC
        LIMIT 1
    """), {"p": payload.phone_e164}).mappings().first()

    if not row:
        raise HTTPException(400, "OTP not found")

    if row["consumed_at"] is not None:
        raise HTTPException(400, "OTP already used")

    if now_utc() > row["expires_at"]:
        raise HTTPException(400, "OTP expired")

    if row["attempts"] >= 5:
        raise HTTPException(400, "Too many attempts")

    if otp_hash(payload.code) != row["code_hash"]:
        db.execute(sa.text("UPDATE auth_otps SET attempts=attempts+1 WHERE id=:id"), {"id": row["id"]})
        db.commit()
        raise HTTPException(400, "Invalid OTP")

    # consume
    db.execute(sa.text("UPDATE auth_otps SET consumed_at=now() WHERE id=:id"), {"id": row["id"]})

    # upsert user
    user = db.execute(sa.text("SELECT id FROM users WHERE phone_e164=:p"), {"p": payload.phone_e164}).mappings().first()
    if user:
        user_id = user["id"]
        db.execute(sa.text("UPDATE users SET last_login_at=now() WHERE id=:id"), {"id": user_id})
    else:
        user_id = db.execute(sa.text("""
            INSERT INTO users (phone_e164, status)
            VALUES (:p, 'active')
            RETURNING id
        """), {"p": payload.phone_e164}).scalar_one()

        # Create a temporary profile (alias required); user can edit later in /me/profile
        # Uses last 4 digits + random suffix to avoid collisions.
        suffix = payload.phone_e164[-4:].replace("+","")
        alias = f"player_{suffix}"
        # Ensure uniqueness quickly
        n = 0
        while True:
            exists = db.execute(sa.text("SELECT 1 FROM user_profiles WHERE alias=:a"), {"a": alias}).first()
            if not exists:
                break
            n += 1
            alias = f"player_{suffix}_{n}"

        # Default gender must be set by user; but gender is required for ladder logic.
        # For now we set 'M' as placeholder and force update later if needed.
        db.execute(sa.text("""
            INSERT INTO user_profiles (user_id, alias, gender, is_public)
            VALUES (:u, :a, 'M', true)
        """), {"u": user_id, "a": alias})

    audit(db, user_id, "auth", str(user_id), "login", {})
    db.commit()

    return TokenOut(
        access_token=create_access_token(str(user_id)),
        refresh_token=create_refresh_token(str(user_id)),
    )

@router.post("/refresh", response_model=TokenOut)
def refresh(payload: RefreshIn, db: Session = Depends(get_db)):
    try:
        decoded = decode_token(payload.refresh_token)
    except Exception:
        raise HTTPException(401, "Invalid refresh token")

    if decoded.get("type") != "refresh":
        raise HTTPException(401, "Invalid token type")

    user_id = decoded.get("sub")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(401, "User not found")
    if user.status != "active":
        raise HTTPException(403, "User blocked")

    return TokenOut(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )
