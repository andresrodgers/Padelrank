from app.db.session import SessionLocal
from app.services.billing import reconcile_subscriptions


def main():
    db = SessionLocal()
    try:
        result = reconcile_subscriptions(db, limit=500)
        db.commit()
        print(
            "ok: reconciliacion billing completada "
            f"(processed={result['processed']}, updated={result['updated']}, skipped={result['skipped']}, errors={result['errors']})"
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
