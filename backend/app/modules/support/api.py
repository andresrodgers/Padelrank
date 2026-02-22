from urllib.parse import quote

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.schemas.support import (
    SupportContactOut,
    SupportTicketCreateIn,
    SupportTicketListOut,
    SupportTicketOut,
)
from app.services.audit import audit

router = APIRouter()


def _build_mailto(user_id: str, plan_code: str) -> SupportContactOut:
    subject = f"Rivio soporte | user:{user_id} | plan:{plan_code}"
    body = (
        "Hola equipo Rivio,%0A%0A"
        "Necesito ayuda con:%0A"
        "- Contexto:%0A"
        "- Pasos para reproducir:%0A"
        "- Resultado esperado:%0A"
        "- Resultado actual:%0A%0A"
        "Gracias."
    )
    mailto = f"mailto:{settings.SUPPORT_CONTACT_EMAIL}?subject={quote(subject)}&body={body}"
    return SupportContactOut(
        to_email=settings.SUPPORT_CONTACT_EMAIL,
        subject_template=subject,
        body_template="Hola equipo Rivio, ...",
        mailto_url=mailto,
    )


@router.get("/contact", response_model=SupportContactOut)
def contact_link(current=Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.execute(
        sa.text(
            """
            SELECT plan_code
            FROM user_entitlements
            WHERE user_id=:u
            """
        ),
        {"u": str(current.id)},
    ).mappings().first()
    plan_code = str((row or {}).get("plan_code") or "FREE")
    return _build_mailto(str(current.id), plan_code)


@router.post("/tickets", response_model=SupportTicketOut)
def create_ticket(payload: SupportTicketCreateIn, current=Depends(get_current_user), db: Session = Depends(get_db)):
    if not settings.SUPPORT_TICKETS_ENABLED:
        raise HTTPException(503, "Soporte in-app deshabilitado temporalmente")

    recent_count = int(
        db.execute(
            sa.text(
                """
                SELECT count(*)
                FROM support_tickets
                WHERE user_id=:u
                  AND created_at >= (now() - interval '24 hours')
                """
            ),
            {"u": str(current.id)},
        ).scalar_one()
    )
    if recent_count >= settings.SUPPORT_MAX_TICKETS_PER_DAY:
        raise HTTPException(429, "Limite diario de tickets alcanzado")

    last_created_at = db.execute(
        sa.text(
            """
            SELECT created_at
            FROM support_tickets
            WHERE user_id=:u
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        {"u": str(current.id)},
    ).scalar_one_or_none()
    if last_created_at is not None:
        min_seconds = int(settings.SUPPORT_MIN_SECONDS_BETWEEN_TICKETS)
        too_soon = db.execute(
            sa.text("SELECT now() < (:last_created_at + make_interval(secs => :min_seconds))"),
            {"last_created_at": last_created_at, "min_seconds": min_seconds},
        ).scalar_one()
        if bool(too_soon):
            raise HTTPException(429, "Debes esperar antes de crear otro ticket")

    row = db.execute(
        sa.text(
            """
            INSERT INTO support_tickets (user_id, category, subject, message, status)
            VALUES (:u, :category, :subject, :message, 'open')
            RETURNING
                id::text AS id,
                category,
                subject,
                message,
                status,
                created_at,
                updated_at
            """
        ),
        {
            "u": str(current.id),
            "category": payload.category,
            "subject": payload.subject.strip(),
            "message": payload.message.strip(),
        },
    ).mappings().one()

    audit(
        db,
        current.id,
        "support_ticket",
        row["id"],
        "created",
        {"category": row["category"]},
    )
    db.commit()
    return SupportTicketOut(**row)


@router.get("/tickets/me", response_model=SupportTicketListOut)
def my_tickets(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        sa.text(
            """
            SELECT
                id::text AS id,
                category,
                subject,
                message,
                status,
                created_at,
                updated_at
            FROM support_tickets
            WHERE user_id=:u
            ORDER BY created_at DESC, id DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {"u": str(current.id), "limit": limit, "offset": offset},
    ).mappings().all()
    out_rows = [SupportTicketOut(**r) for r in rows]
    next_offset = offset + limit if len(out_rows) == limit else None
    return SupportTicketListOut(rows=out_rows, limit=limit, offset=offset, next_offset=next_offset)
