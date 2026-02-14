from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog

def audit(db: Session, actor_user_id, entity_type: str, entity_id: str, action: str, data: dict):
    row = AuditLog(
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        data=data or {},
    )
    db.add(row)
