import sqlalchemy as sa

from app.db.session import SessionLocal


def _anonymize_user(db, user_id: str):
    alias = f"deleted_{user_id.replace('-', '')}"

    db.execute(
        sa.text(
            """
            UPDATE users
            SET
                phone_e164=NULL,
                email=NULL,
                status='deleted'
            WHERE id=:u
            """
        ),
        {"u": user_id},
    )
    db.execute(sa.text("DELETE FROM auth_credentials WHERE user_id=:u"), {"u": user_id})
    db.execute(sa.text("DELETE FROM auth_identities WHERE user_id=:u"), {"u": user_id})
    db.execute(
        sa.text(
            """
            UPDATE auth_sessions
            SET revoked_at=COALESCE(revoked_at, now()),
                revoked_reason=COALESCE(revoked_reason, 'account_deleted')
            WHERE user_id=:u
            """
        ),
        {"u": user_id},
    )
    db.execute(
        sa.text(
            """
            UPDATE user_profiles
            SET
                alias=:alias,
                is_public=false,
                city=NULL,
                country='ZZ',
                first_name=NULL,
                last_name=NULL,
                birthdate=NULL,
                avatar_mode='preset',
                avatar_preset_key='default_1',
                avatar_url=NULL,
                updated_at=now()
            WHERE user_id=:u
            """
        ),
        {"u": user_id, "alias": alias},
    )


def main():
    db = SessionLocal()
    try:
        due = db.execute(
            sa.text(
                """
                SELECT
                    id::text AS id,
                    user_id::text AS user_id
                FROM account_deletion_requests
                WHERE cancelled_at IS NULL
                  AND executed_at IS NULL
                  AND scheduled_for <= now()
                ORDER BY scheduled_for ASC, id ASC
                FOR UPDATE
                """
            )
        ).mappings().all()

        processed = 0
        for row in due:
            _anonymize_user(db, row["user_id"])
            db.execute(
                sa.text(
                    """
                    UPDATE account_deletion_requests
                    SET executed_at=now()
                    WHERE id=:id
                    """
                ),
                {"id": row["id"]},
            )
            processed += 1

        db.commit()
        print(f"ok: eliminaciones de cuenta procesadas={processed}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
