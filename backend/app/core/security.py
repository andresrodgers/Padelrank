import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt

from app.core.config import settings

ALGO = "HS256"

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def otp_hash(code: str) -> str:
    # Stable hash for OTP verification (peppered)
    raw = (settings.OTP_PEPPER + ":" + code).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def pii_hash(value: str, purpose: str = "pii") -> str:
    raw = (settings.OTP_PEPPER + ":" + purpose + ":" + value).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def create_access_token(sub: str) -> str:
    return create_access_token_for_session(sub, sid=None)

def create_access_token_for_session(sub: str, sid: str | None) -> str:
    exp = now_utc() + timedelta(minutes=settings.JWT_ACCESS_MINUTES)
    payload = {"sub": sub, "type": "access", "exp": exp}
    if sid is not None:
        payload["sid"] = sid
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGO)

def create_refresh_token(sub: str) -> str:
    return create_refresh_token_for_session(sub, sid=None)

def create_refresh_token_for_session(sub: str, sid: str | None) -> str:
    exp = now_utc() + timedelta(days=settings.JWT_REFRESH_DAYS)
    payload = {"sub": sub, "type": "refresh", "exp": exp}
    if sid is not None:
        payload["sid"] = sid
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGO)

def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGO])

def random_otp_code() -> str:
    # 6 digits
    return f"{secrets.randbelow(1_000_000):06d}"

def hash_refresh_token(token: str) -> str:
    raw = (settings.JWT_SECRET + ":" + token).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def hash_password(password: str) -> str:
    raw = password.encode("utf-8")
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("utf-8")

def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False
