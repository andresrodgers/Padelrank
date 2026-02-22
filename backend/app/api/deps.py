from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User

bearer = HTTPBearer()


def _get_user_from_access_token(creds: HTTPAuthorizationCredentials, db: Session) -> User:
    try:
        payload = decode_token(creds.credentials)
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalido")
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Tipo de token invalido")
    user_id = payload.get("sub")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return user


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    user = _get_user_from_access_token(creds, db)
    if user.status != "active":
        raise HTTPException(status_code=403, detail="Usuario bloqueado")
    return user


def get_authenticated_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    user = _get_user_from_access_token(creds, db)
    if user.status not in {"active", "pending_deletion"}:
        raise HTTPException(status_code=403, detail="Usuario bloqueado")
    return user
