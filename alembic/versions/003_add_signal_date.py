"""Add signal_date (yyyy-mm-dd) column to sticky_notes.

Revision ID: 003_add_signal_date
Revises: 002_add_position_type
Create Date: 2026-08-21 00:00:00.000000

Adds a DATE column defaulting to CURRENT_DATE so every sticky note records
the calendar date it was discovered. Existing rows are backfilled with the
current date via the server default.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '003_add_signal_date'
down_revision = '002_add_position_type'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add signal_date column defaulting to CURRENT_DATE."""
    op.add_column(
        'sticky_notes',
        sa.Column(
            'signal_date',
            sa.Date(),
            nullable=False,
            server_default=sa.func.current_date(),
        )
    )
    op.create_index(
        'idx_sticky_notes_signal_date',
        'sticky_notes',
        ['signal_date'],
    )


def downgrade() -> None:
    """Remove signal_date column."""
    op.drop_index('idx_sticky_notes_signal_date', table_name='sticky_notes')
    op.drop_column('sticky_notes', 'signal_date')
