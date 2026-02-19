"""sanitize auth audit entity_id

Revision ID: 0007_audit_phone_hash
Revises: 0006_alias_lower_index_backfill
Create Date: 2026-02-19
"""

from alembic import op


revision = "0007_audit_phone_hash"
down_revision = "0006_alias_lower_index_backfill"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE audit_log
        SET entity_id = 'phone_sha256:' || encode(digest(entity_id, 'sha256'), 'hex')
        WHERE entity_type='auth'
          AND action='otp_requested'
          AND entity_id LIKE '+%';
    """)


def downgrade():
    # Irreversible by design: plain phone numbers are intentionally not restored.
    pass
