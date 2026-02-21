from app.db.session import SessionLocal
from app.services.analytics import rebuild_analytics


def main():
    db = SessionLocal()
    try:
        rebuild_analytics(db)
        db.commit()
        print("ok: analitica reconstruida")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
