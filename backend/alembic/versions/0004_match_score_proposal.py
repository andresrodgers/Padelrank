from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_match_score_proposal"
down_revision = "76cbbd7ab342"  # ajusta al id real de tu 0003
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("matches", sa.Column("proposed_score_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("matches", sa.Column("proposed_winner_team_no", sa.SmallInteger(), nullable=True))
    op.add_column("matches", sa.Column("proposed_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("matches", sa.Column("proposed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("matches", sa.Column("proposal_count", sa.Integer(), nullable=False, server_default="0"))

def downgrade():
    op.drop_column("matches", "proposal_count")
    op.drop_column("matches", "proposed_at")
    op.drop_column("matches", "proposed_by")
    op.drop_column("matches", "proposed_winner_team_no")
    op.drop_column("matches", "proposed_score_json")
