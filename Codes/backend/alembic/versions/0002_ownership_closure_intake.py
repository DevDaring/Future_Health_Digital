"""case ownership, documented closure and reviewer-added results

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-18 03:10:00
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('screening_events', sa.Column('facility', sa.String(length=120), nullable=True))
    op.create_table('loop_closures',
    sa.Column('loop_id', sa.Uuid(), nullable=False),
    sa.Column('outcome', sa.String(length=40), nullable=False),
    sa.Column('seen_by', sa.String(length=160), nullable=False),
    sa.Column('visit_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('next_step', sa.String(length=200), nullable=False),
    sa.Column('patient_informed', sa.Boolean(), nullable=False),
    sa.Column('report_shared_with', sa.String(length=160), nullable=False),
    sa.Column('closed_by', sa.Uuid(), nullable=True),
    sa.Column('closed_by_name', sa.String(length=120), nullable=False),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['closed_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['loop_id'], ['care_loops.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('loop_id')
    )


def downgrade() -> None:
    op.drop_table('loop_closures')
    op.drop_column('screening_events', 'facility')
