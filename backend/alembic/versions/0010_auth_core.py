"""auth core entities and rate-limit table

Revision ID: 0010_auth_core
Revises: 0009_user_contact_change
Create Date: 2026-02-19
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_auth_core"
down_revision = "0009_user_contact_change"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "auth_identities",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("is_verified", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("kind in ('phone','email')", name="ck_auth_identity_kind"),
        sa.UniqueConstraint("kind", "value", name="uq_auth_identity_kind_value"),
        sa.UniqueConstraint("user_id", "kind", name="uq_auth_identity_user_kind"),
    )
    op.create_index("ix_auth_identities_user_verified", "auth_identities", ["user_id", "is_verified"])

    op.create_table(
        "auth_credentials",
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("password_updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("refresh_hash", sa.Text, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.Text, nullable=True),
        sa.Column("replaced_by", sa.Uuid, sa.ForeignKey("auth_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_auth_sessions_user_active", "auth_sessions", ["user_id", "revoked_at", sa.text("created_at DESC")])

    op.create_table(
        "auth_login_attempts",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("login_key_hash", sa.Text, nullable=False),
        sa.Column("success", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_auth_login_attempts_key_created", "auth_login_attempts", ["login_key_hash", sa.text("created_at DESC")])

    op.add_column("auth_otps", sa.Column("purpose", sa.Text, nullable=True))
    op.execute("UPDATE auth_otps SET purpose='register' WHERE purpose IS NULL;")
    op.execute("ALTER TABLE auth_otps ALTER COLUMN purpose SET NOT NULL;")
    op.execute("ALTER TABLE auth_otps DROP CONSTRAINT IF EXISTS ck_auth_otps_purpose;")
    op.execute("""
        ALTER TABLE auth_otps
        ADD CONSTRAINT ck_auth_otps_purpose
        CHECK (purpose IN ('register','password_reset','contact_change'));
    """)
    op.create_index(
        "ix_auth_otps_contact_purpose_created",
        "auth_otps",
        ["contact_kind", "contact_value", "purpose", sa.text("created_at DESC")],
    )

    # Backfill verified identities from existing users.
    op.execute("""
        INSERT INTO auth_identities (user_id, kind, value, is_verified, verified_at)
        SELECT id, 'phone', phone_e164, true, now()
        FROM users
        WHERE phone_e164 IS NOT NULL
        ON CONFLICT (kind, value) DO NOTHING;
    """)
    op.execute("""
        INSERT INTO auth_identities (user_id, kind, value, is_verified, verified_at)
        SELECT id, 'email', lower(email), true, now()
        FROM users
        WHERE email IS NOT NULL
        ON CONFLICT (kind, value) DO NOTHING;
    """)


def downgrade():
    op.drop_index("ix_auth_otps_contact_purpose_created", table_name="auth_otps")
    op.execute("ALTER TABLE auth_otps DROP CONSTRAINT IF EXISTS ck_auth_otps_purpose;")
    op.drop_column("auth_otps", "purpose")

    op.drop_index("ix_auth_login_attempts_key_created", table_name="auth_login_attempts")
    op.drop_table("auth_login_attempts")

    op.drop_index("ix_auth_sessions_user_active", table_name="auth_sessions")
    op.drop_table("auth_sessions")

    op.drop_table("auth_credentials")

    op.drop_index("ix_auth_identities_user_verified", table_name="auth_identities")
    op.drop_table("auth_identities")
