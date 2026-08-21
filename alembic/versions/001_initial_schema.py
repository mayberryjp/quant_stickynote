"""Initial schema creation with sticky_notes and query_executions tables.

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-08-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create initial schema."""
    # Create sticky_notes table
    op.create_table(
        'sticky_notes',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('symbol', sa.String(10), nullable=False),
        sa.Column('trigger_reason', sa.String(255), nullable=False),
        sa.Column('buy_price', sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('source_query_id', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('active', 'reviewed', 'cancelled', 'executed')", name='ck_status'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_sticky_notes_symbol', 'sticky_notes', ['symbol'], unique=False)
    op.create_index('idx_sticky_notes_created_at', 'sticky_notes', ['created_at'], unique=False)
    op.create_index('idx_sticky_notes_status', 'sticky_notes', ['status'], unique=False)

    # Create query_executions table
    op.create_table(
        'query_executions',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('query_id', sa.String(50), nullable=False),
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('row_count', sa.Integer(), nullable=True),
        sa.Column('signals_extracted', sa.Integer(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('success', 'error', 'skipped')", name='ck_execution_status'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_query_executions_query_id', 'query_executions', ['query_id', 'executed_at'], unique=False)


def downgrade() -> None:
    """Drop initial schema."""
    op.drop_table('query_executions')
    op.drop_table('sticky_notes')
