# Database Migration Guide

This guide explains how to set up and manage the database schema for the quant_stickynote service using Alembic.

## Overview

- **Tool**: Alembic (SQLAlchemy migration framework)
- **Database**: PostgreSQL 12+
- **Configuration**: `alembic.ini` in project root

## Quick Start

### 1. Initialize Database (Fresh Install)

If you're setting up the database from scratch:

```bash
# Set database URL (adjust credentials/host as needed)
export DATABASE_URL="postgresql://quant_user:quant_pass@localhost:5432/quant_stickynote"

# Run initial migration
alembic upgrade head
```

This creates:
- `sticky_notes` table (for storing trading signals)
- `query_executions` table (for audit log)
- `alembic_version` table (for migration tracking)

### 2. Upgrade Existing Database

If you already have the sticky_notes table and want to add new columns:

```bash
export DATABASE_URL="postgresql://quant_user:quant_pass@localhost:5432/quant_stickynote"

# Show current migration version
alembic current

# Show available upgrades
alembic upgrade --sql head

# Apply all pending migrations
alembic upgrade head
```

### 3. Rollback Changes

To undo migrations (careful in production!):

```bash
# See current and available versions
alembic history

# Rollback one migration
alembic downgrade -1

# Rollback to specific version
alembic downgrade 001_initial_schema
```

## Schema Overview

### Migration: 001_initial_schema

**Status**: Initial schema (recommended for new deployments)

**Creates**:

#### sticky_notes table
```sql
CREATE TABLE sticky_notes (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    trigger_reason VARCHAR(255) NOT NULL,
    buy_price NUMERIC(10, 4) NOT NULL,
    position_type VARCHAR(10) NOT NULL DEFAULT 'LONG'
        CHECK (position_type IN ('LONG', 'SHORT')),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    source_query_id VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'reviewed', 'cancelled', 'executed')),
    notes TEXT,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(symbol, trigger_reason, DATE(created_at))
);

-- Indexes for performance
CREATE INDEX idx_sticky_notes_symbol ON sticky_notes(symbol);
CREATE INDEX idx_sticky_notes_created_at ON sticky_notes(created_at DESC);
CREATE INDEX idx_sticky_notes_status ON sticky_notes(status);
CREATE INDEX idx_sticky_notes_position_type ON sticky_notes(position_type);
```

**Fields**:
- `id`: Auto-incrementing primary key
- `symbol`: Stock ticker (e.g., AAPL, TSLA)
- `trigger_reason`: Name of query/rule that generated signal
- `buy_price`: Recommended entry price (4 decimal places)
- `position_type`: Trade direction - `'LONG'` (buy/bull) or `'SHORT'` (sell/bear)
- `created_at`: UTC timestamp when signal discovered
- `source_query_id`: Reference to query definition file
- `status`: Signal lifecycle (active, reviewed, cancelled, executed)
- `notes`: Optional trader notes
- `updated_at`: Last modified timestamp

#### query_executions table
```sql
CREATE TABLE query_executions (
    id BIGSERIAL PRIMARY KEY,
    query_id VARCHAR(50) NOT NULL,
    executed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    row_count INT,
    signals_extracted INT,
    duration_ms INT,
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('success', 'error', 'skipped')),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_query_executions_query_id ON query_executions(query_id, executed_at DESC);
```

**Purpose**: Audit log for query execution history

### Migration: 002_add_position_type (Optional)

**Status**: For upgrading existing schemas without position_type

**Changes**:
- Adds `position_type` column to sticky_notes (if missing)
- Defaults to `'LONG'`
- Creates index on position_type for query performance

**Use case**: If you have an older schema and want to add the position_type column

## Key Field: position_type

### Purpose
Tracks the direction of the trading signal:
- **LONG**: Buy or bullish signal (expect price to go up)
- **SHORT**: Sell or bearish signal (expect price to go down)

### How Query Definitions Use It

Define `position_type_column` in query JSON to specify which database column contains the direction:

```json
{
  "id": "short_squeeze_001",
  "name": "Short Squeeze Scanner",
  "enabled": true,
  "external_database": {
    "url": "${DATA_WAREHOUSE_URL}"
  },
  "source_query": "SELECT symbol, price, short_interest_pct FROM stocks WHERE short_interest_pct > 0.2",
  "signal_extraction": {
    "symbol_column": "symbol",
    "buy_price_column": "price",
    "position_type_column": "position_type",
    "filter_expression": "short_interest_pct > 0.15"
  }
}
```

### Defaults
- If `position_type_column` is omitted from query definition → defaults to `'LONG'`
- Database column default → `'LONG'`

### Validation
- Only values: `'LONG'` or `'SHORT'` (case-sensitive, uppercase)
- Database CHECK constraint enforces valid values
- ORM uses Python Enum for type safety

## Alembic Command Reference

```bash
# Show current migration version
alembic current

# Show all migrations and their status
alembic history

# Show what the next upgrade will do (SQL preview)
alembic upgrade --sql head

# Apply all pending migrations
alembic upgrade head

# Apply one migration
alembic upgrade +1

# Rollback last migration
alembic downgrade -1

# Rollback to specific revision
alembic downgrade 001_initial_schema

# Create new migration (after changing models.py)
alembic revision --autogenerate -m "Description of change"
```

## Troubleshooting

### Error: "Can't locate revision identified by '...'"
- Ensure DATABASE_URL environment variable is set correctly
- Check that the migration files exist in `alembic/versions/`
- Verify psycopg is installed: `pip install psycopg[binary]`

### Error: "Column 'position_type' already exists"
- Migration has already been applied
- Check current version: `alembic current`

### Error: "relation 'sticky_notes' does not exist"
- Database schema hasn't been initialized yet
- Run: `alembic upgrade head` to create all tables

### Manual Database Check
```bash
# Connect to PostgreSQL
psql postgresql://user:password@localhost:5432/quant_stickynote

# Check migration status
SELECT * FROM alembic_version;

# List tables
\dt

# Describe sticky_notes table
\d sticky_notes

# Check sticky_notes columns and constraints
SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name='sticky_notes';
```

## Production Considerations

1. **Backup Before Migration**: Always backup production database before running migrations
   ```bash
   pg_dump postgresql://user:password@host:5432/db > backup.sql
   ```

2. **Dry Run First**: Preview changes before applying
   ```bash
   alembic upgrade --sql head  # See the SQL
   ```

3. **Monitor Performance**: Large data migrations may lock tables
   - Review migration duration on dev/staging first
   - Schedule during maintenance windows for large tables

4. **Rollback Plan**: Keep downgrade SQL available
   ```bash
   alembic downgrade --sql 001_initial_schema
   ```

## Environment Variables

Required for all Alembic commands:

```bash
# PostgreSQL connection string
export DATABASE_URL="postgresql://quant_user:password@localhost:5432/quant_stickynote"

# Optional: Log level for migration output
export SQLALCHEMY_ECHO=true  # Verbose SQL logging
```

## References

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [SQLAlchemy ORM Models](../src/quant_stickynote/models.py)
- [Query Definition Format](../queries/README.md)
- [SPEC.md - Database Schema](../SPEC.md#database-schema)
