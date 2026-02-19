"""email + generic auth contact

Revision ID: 0008_email_contact_auth
Revises: 0007_audit_phone_hash
Create Date: 2026-02-19
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_email_contact_auth"
down_revision = "0007_audit_phone_hash"
branch_labels = None
depends_on = None


def upgrade():
    # users: allow phone OR email and keep at least one contact
    op.add_column("users", sa.Column("email", sa.Text(), nullable=True))
    op.execute("ALTER TABLE users ALTER COLUMN phone_e164 DROP NOT NULL;")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_contact_required;")
    op.execute("""
        ALTER TABLE users
        ADD CONSTRAINT ck_users_contact_required
        CHECK (phone_e164 IS NOT NULL OR email IS NOT NULL);
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_indexes
                WHERE schemaname='public' AND indexname='uq_users_email_lower'
            ) THEN
                CREATE UNIQUE INDEX uq_users_email_lower
                ON users (lower(email))
                WHERE email IS NOT NULL;
            END IF;
        END $$;
    """)

    # auth_otps: support email and phone using normalized generic contact fields
    op.add_column("auth_otps", sa.Column("contact_kind", sa.Text(), nullable=True))
    op.add_column("auth_otps", sa.Column("contact_value", sa.Text(), nullable=True))
    op.execute("""
        UPDATE auth_otps
        SET contact_kind='phone',
            contact_value=phone_e164
        WHERE contact_kind IS NULL OR contact_value IS NULL;
    """)
    op.execute("ALTER TABLE auth_otps ALTER COLUMN contact_kind SET NOT NULL;")
    op.execute("ALTER TABLE auth_otps ALTER COLUMN contact_value SET NOT NULL;")
    op.execute("ALTER TABLE auth_otps DROP CONSTRAINT IF EXISTS ck_auth_otps_contact_kind;")
    op.execute("""
        ALTER TABLE auth_otps
        ADD CONSTRAINT ck_auth_otps_contact_kind
        CHECK (contact_kind IN ('phone', 'email'));
    """)
    op.create_index(
        "ix_auth_otps_contact_expires",
        "auth_otps",
        ["contact_kind", "contact_value", "expires_at"],
    )


def downgrade():
    op.drop_index("ix_auth_otps_contact_expires", table_name="auth_otps")
    op.execute("ALTER TABLE auth_otps DROP CONSTRAINT IF EXISTS ck_auth_otps_contact_kind;")
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM auth_otps WHERE contact_kind <> 'phone'
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade: email OTP rows exist in auth_otps.';
            END IF;
        END $$;
    """)
    op.drop_column("auth_otps", "contact_value")
    op.drop_column("auth_otps", "contact_kind")

    op.execute("DROP INDEX IF EXISTS uq_users_email_lower;")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_contact_required;")
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM users WHERE phone_e164 IS NULL
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade: users without phone_e164 exist.';
            END IF;
        END $$;
    """)
    op.execute("ALTER TABLE users ALTER COLUMN phone_e164 SET NOT NULL;")
    op.drop_column("users", "email")
