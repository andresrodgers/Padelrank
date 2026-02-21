from datetime import timedelta

import sqlalchemy as sa

from app.core.config import settings
from app.core.security import now_utc
from app.db.session import SessionLocal


def main():
    db = SessionLocal()
    try:
        now = now_utc()
        otp_cutoff = now - timedelta(days=settings.AUTH_OTP_RETENTION_DAYS)
        login_cutoff = now - timedelta(days=settings.AUTH_LOGIN_ATTEMPTS_RETENTION_DAYS)
        contact_cutoff = now - timedelta(days=settings.USER_CONTACT_CHANGES_RETENTION_DAYS)

        deleted_otps = db.execute(sa.text("""
            DELETE FROM auth_otps
            WHERE
              (consumed_at IS NOT NULL AND consumed_at < :otp_cutoff)
              OR
              (expires_at < :otp_cutoff)
        """), {"otp_cutoff": otp_cutoff}).rowcount

        deleted_login_attempts = db.execute(sa.text("""
            DELETE FROM auth_login_attempts
            WHERE created_at < :login_cutoff
        """), {"login_cutoff": login_cutoff}).rowcount

        deleted_contact_changes = db.execute(sa.text("""
            DELETE FROM user_contact_changes
            WHERE
              (consumed_at IS NOT NULL AND consumed_at < :contact_cutoff)
              OR
              (expires_at < :contact_cutoff)
        """), {"contact_cutoff": contact_cutoff}).rowcount

        db.commit()
        print(
            "ok: limpieza completada "
            f"(auth_otps={deleted_otps}, "
            f"auth_login_attempts={deleted_login_attempts}, "
            f"user_contact_changes={deleted_contact_changes})"
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
