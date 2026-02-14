import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGO = "HS256"

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def otp_hash(code: str) -> str:
    # Stable hash for OTP verification (peppered)
    raw = (settings.OTP_PEPPER + ":" + code).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def create_access_token(sub: str) -> str:
    exp = now_utc() + timedelta(minutes=settings.JWT_ACCESS_MINUTES)
    payload = {"sub": sub, "type": "access", "exp": exp}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGO)

def create_refresh_token(sub: str) -> str:
    exp = now_utc() + timedelta(days=settings.JWT_REFRESH_DAYS)
    payload = {"sub": sub, "type": "refresh", "exp": exp}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGO)

def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGO])

def random_otp_code() -> str:
    # 6 digits
    return f"{secrets.randbelow(1_000_000):06d}"
