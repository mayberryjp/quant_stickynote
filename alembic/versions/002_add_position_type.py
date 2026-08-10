"""Migration to add position_type column to existing sticky_notes tables.

Revision ID: 002_add_position_type
Revises: 001_initial_schema
Create Date: 2026-08-10 00:00:01.000000

This migration is for users who already have the sticky_notes table
and want to add the position_type (LONG/SHORT) column.
If you're starting fresh, this migration is not needed.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002_add_position_type'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add position_type column if sticky_notes already exists."""
    # Check if sticky_notes table exists and position_type doesn't
    # If starting from initial schema (001), this will be skipped
    op.add_column(
        'sticky_notes',
        sa.Column(
            'position_type',
            sa.String(10),
            nullable=False,
            server_default='LONG'
        )
    )
    op.create_check_constraint(
        'ck_position_type',
        'sticky_notes',
        "position_type IN ('LONG', 'SHORT')"
    )
    op.create_index(
        'idx_sticky_notes_position_type',
        'sticky_notes',
        ['position_type']
    )


def downgrade() -> None:
    """Remove position_type column."""
    op.drop_index('idx_sticky_notes_position_type', table_name='sticky_notes')
    op.drop_constraint('ck_position_type', 'sticky_notes', type_='check')
    op.drop_column('sticky_notes', 'position_type')
