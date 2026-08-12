# Query Definitions Guide

This directory contains JSON query definitions that the quant_stickynote service uses to discover trading signals.

## Overview

Each JSON file in this directory defines:
- How to connect to an external database
- What SQL query to run
- How to extract trading signals from the results
- Deduplication and scheduling rules

**Example filename**: `momentum_breakout.json`

## Query Definition Schema

```json
{
  "id": "unique_query_identifier",
  "name": "Human-readable query name",
  "description": "What this query looks for and why",
  "enabled": true,
  "external_database": {
    "url": "postgresql://user:password@host:5432/database",
    "pool_size": 5,
    "pool_recycle": 3600
  },
  "source_query": "SELECT symbol, price FROM table WHERE condition",
  "signal_extraction": {
    "symbol_column": "column_name_for_stock_symbol",
    "buy_price_column": "column_name_for_entry_price",
    "trigger_reason_template": "Optional: Why this signal triggered",
    "filter_expression": "Optional: Additional filtering logic"
  },
  "dedup_key_ttl_hours": 24,
  "max_results_per_run": 100,
  "timeout_seconds": 300
}
```

## Field Descriptions

### Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | ✅ | Unique identifier (lowercase, no spaces). Used for logging and API lookups. |
| `name` | string | ✅ | Human-readable name (e.g., "RSI Oversold Signals"). |
| `description` | string | ✅ | What this query detects and why (visible in logs). |
| `enabled` | boolean | ✅ | Set to `true` to run, `false` to skip. |
| `external_database` | object | ✅ | Database connection details. |
| `source_query` | string | ✅ | SQL query to run (must return rows). |
| `signal_extraction` | object | ✅ | How to extract signals from query results. |
| `dedup_key_ttl_hours` | integer | ✅ | Hours before allowing duplicate signals (default: 24). |
| `max_results_per_run` | integer | ❌ | Max signals per execution (default: 100, 0=unlimited). |
| `timeout_seconds` | integer | ❌ | Query timeout (default: 300). |

### external_database

```json
{
  "url": "postgresql://user:password@host:5432/database",
  "pool_size": 5,
  "pool_recycle": 3600
}
```

| Field | Type | Description |
|-------|------|-------------|
| `url` | string | Full database connection string. **Do NOT commit passwords—use environment variables.** |
| `pool_size` | integer | Connection pool size (default: 5). |
| `pool_recycle` | integer | Seconds before recycling connections (default: 3600). |

**URL Format**:
```
postgresql://username:password@hostname:port/database
```

**Using Environment Variables**:
Instead of hardcoding credentials, use this pattern:
```json
{
  "url": "${DATABASE_WAREHOUSE_URL}",
  "pool_size": 5
}
```

Then set environment variable before running service:
```bash
export DATABASE_WAREHOUSE_URL="postgresql://user:pass@host:5432/db"
```

### signal_extraction

```json
{
  "symbol_column": "ticker",
  "buy_price_column": "suggested_entry",
  "position_type_column": "trade_direction",
  "trigger_reason_template": "RSI Oversold Signal",
  "filter_expression": "confidence > 0.8"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `symbol_column` | string | ✅ | Column name containing stock ticker (e.g., "symbol", "ticker"). |
| `buy_price_column` | string | ✅ | Column name with recommended buy price. |
| `position_type_column` | string | ❌ | Column name specifying trade direction ("LONG" or "SHORT"). If omitted, defaults to "LONG". |
| `trigger_reason_template` | string | ❌ | Text to store in `trigger_reason` field. If omitted, defaults to query name. |
| `filter_expression` | string | ❌ | Additional Python expression to filter signals (see below). |

### Filter Expression

Apply custom Python logic to filter/transform signals:

```json
{
  "symbol_column": "symbol",
  "buy_price_column": "price",
  "filter_expression": "price > 10 and price < 1000"
}
```

Available variables in filter expression:
- Column names as Python variables: `symbol`, `price`, `volume`, etc.
- Built-in functions: `len()`, `abs()`, `str()`, `float()`, `int()`
- Operators: `and`, `or`, `not`, `>`, `<`, `==`, `!=`

**Examples**:
```python
# Only signals with price between $10 and $500
price > 10 and price < 500

# Exclude penny stocks
price >= 1

# Only high-volume trades
volume > 1000000

# Symbols starting with 'A'
str(symbol).startswith('A')

# Complex: momentum above threshold AND volume spike
momentum_score > 0.7 and volume_ratio > 1.5
```

## Examples

### Example 1: RSI Oversold Detection

**File**: `queries/rsi_oversold.json`

```json
{
  "id": "rsi_oversold_001",
  "name": "RSI Oversold Reversal",
  "description": "Identifies stocks with RSI < 30, potentially oversold and ready for reversal",
  "enabled": true,
  "external_database": {
    "url": "${DATA_WAREHOUSE_URL}",
    "pool_size": 5
  },
  "source_query": "SELECT symbol, close_price, rsi_14 FROM daily_technicals WHERE rsi_14 < 30 AND DATE(scan_date) = CURRENT_DATE ORDER BY rsi_14 ASC",
  "signal_extraction": {
    "symbol_column": "symbol",
    "buy_price_column": "close_price",
    "position_type_column": "trade_direction",
    "trigger_reason_template": "RSI Oversold - Potential Reversal",
    "filter_expression": "close_price > 5 and close_price < 1000"
  },
  "dedup_key_ttl_hours": 48,
  "max_results_per_run": 50
}
```

### Example 2: Earnings Announcement

**File**: `queries/earnings_announcement.json`

```json
{
  "id": "earnings_001",
  "name": "Pre-Earnings Volatility Play",
  "description": "Stocks with earnings announcements in next 5 days and elevated implied volatility",
  "enabled": true,
  "external_database": {
    "url": "${OPTIONS_ANALYSIS_URL}"
  },
  "source_query": "SELECT ticker, current_price, implied_vol FROM options_analysis WHERE days_to_earnings <= 5 AND implied_vol > 0.4 AND current_price > 10 ORDER BY implied_vol DESC LIMIT 30",
  "signal_extraction": {
    "symbol_column": "ticker",
    "buy_price_column": "current_price",
    "trigger_reason_template": "Earnings Volatility Setup"
  },
  "dedup_key_ttl_hours": 72,
  "max_results_per_run": 30
}
```

### Example 3: Moving Average Crossover

**File**: `queries/ma_crossover.json`

```json
{
  "id": "ma_crossover_001",
  "name": "50/200 Moving Average Crossover",
  "description": "Bullish crossovers where 50-day MA crosses above 200-day MA",
  "enabled": false,
  "external_database": {
    "url": "${HISTORICAL_DATA_URL}"
  },
  "source_query": "SELECT symbol, close_price, ma_50, ma_200 FROM daily_ma WHERE close_date = CURRENT_DATE AND ma_50 > ma_200 AND LAG(ma_50) OVER (PARTITION BY symbol ORDER BY close_date) <= LAG(ma_200) OVER (PARTITION BY symbol ORDER BY close_date)",
  "signal_extraction": {
    "symbol_column": "symbol",
    "buy_price_column": "close_price",
    "position_type_column": "position_type",
    "trigger_reason_template": "Golden Cross - 50MA above 200MA",
    "filter_expression": "ma_50 > ma_200 * 0.99 and ma_50 < ma_200 * 1.05"
  },
  "dedup_key_ttl_hours": 24,
  "max_results_per_run": 100
}
```

### Example 4: Insider Buying

**File**: `queries/insider_buying.json`

```json
{
  "id": "insider_buying_001",
  "name": "Significant Insider Buying",
  "description": "Executives buying their company stock at high confidence levels",
  "enabled": false,
  "external_database": {
    "url": "${INSIDER_DATA_URL}"
  },
  "source_query": "SELECT symbol, stock_price, exec_title, position_type FROM insider_transactions WHERE transaction_type = 'BUY' AND confidence_score >= 0.8 AND DATE(transaction_date) = CURRENT_DATE",
  "signal_extraction": {
    "symbol_column": "symbol",
    "buy_price_column": "stock_price",
    "position_type_column": "position_type",
    "trigger_reason_template": "Insider Buying by Executive",
    "filter_expression": "exec_title in ['CEO', 'CFO', 'President']"
  },
  "dedup_key_ttl_hours": 168,
  "max_results_per_run": 20
}
```

## Best Practices

### 1. Query Optimization
- Add `WHERE` clauses to filter at source (don't fetch unnecessary data)
- Use indexes on columns in WHERE conditions
- Order by most important signals first
- Limit results when possible

❌ Bad:
```sql
SELECT * FROM all_stocks
```

✅ Good:
```sql
SELECT symbol, price, volume 
FROM all_stocks 
WHERE volume > 1000000 
  AND price > 10 
ORDER BY volume DESC 
LIMIT 100
```

### 2. Deduplication Strategy
- Set `dedup_key_ttl_hours` based on signal frequency
- Daily signals: 24 hours
- Intraday momentum: 4-8 hours
- Long-term trends: 48-72 hours

```json
{
  "dedup_key_ttl_hours": 24
}
```

### 3. Credentials & Secrets
❌ NEVER hardcode passwords:
```json
{
  "url": "postgresql://user:MySecretPassword123@warehouse.db"
}
```

✅ Always use environment variables:
```json
{
  "url": "${DATABASE_URL}"
}
```

Then set before running:
```bash
export DATABASE_URL="postgresql://user:password@host:5432/db"
```

Or in `.env` file:
```
DATA_WAREHOUSE_URL=postgresql://user:pass@host:5432/db
```

### 4. Testing Queries
Before enabling a query:

```bash
# 1. Test the external database connection
psql postgresql://user:pass@host:5432/database -c "SELECT COUNT(*) FROM your_table"

# 2. Verify your SQL query works
psql postgresql://user:pass@host:5432/database -c "SELECT symbol, price FROM your_table LIMIT 5"

# 3. Check signal extraction
# (Can paste into local test)

# 4. Test filter expression with sample data
# (Import sample row and verify filter_expression works)

# 5. Enable in JSON file
# Set "enabled": true

# 6. Verify service loads it
curl http://localhost:8080/queries | jq '.[] | select(.id=="your_query_id")'

# 7. Check execution history
psql postgresql://localhost/quant_stickynote -c "SELECT * FROM query_executions WHERE query_id='your_query_id' ORDER BY executed_at DESC LIMIT 5"
```

### 5. Documentation in Comments
Add explanatory comments to complex queries:

```json
{
  "id": "complex_signal_001",
  "name": "Complex Multi-Factor Signal",
  "description": "Combines multiple technical indicators to reduce false signals",
  "source_query": "SELECT symbol, price FROM signals WHERE rsi < 30 AND macd_histogram < 0 AND volume > ma_volume * 1.5",
  "signal_extraction": {
    "symbol_column": "symbol",
    "buy_price_column": "price",
    "trigger_reason_template": "Multi-Factor Confluence: RSI Oversold + MACD Bearish Divergence + Volume Spike"
  }
}
```

## Troubleshooting

### Query not executing
- Check `enabled: true`
- Verify `external_database.url` is correct
- Test connection manually: `psql <connection_string>`
- Check service logs for connection errors

### No signals extracted
- Verify `source_query` returns rows (run manually)
- Check column names match `symbol_column` and `buy_price_column`
- Test `filter_expression` with sample data
- Check `max_results_per_run` limit

### Duplicate signals appearing
- Increase `dedup_key_ttl_hours`
- Verify query doesn't return duplicates
- Check `UNIQUE(symbol, trigger_reason, DATE(created_at))` constraint

### Performance slow
- Add indexes to frequently queried columns
- Reduce `pool_size` if connections are limited
- Use `max_results_per_run` to limit fetches
- Consider moving query to run less frequently

## API Endpoints for Queries

### List all queries
```bash
curl http://localhost:8080/queries
```

### View query execution history
```bash
curl http://localhost:8080/queries/rsi_oversold_001/executions?limit=20
```

### Get last execution status
```bash
curl http://localhost:8080/queries/rsi_oversold_001/last-execution
```

## Adding Your First Query

1. **Create file**: `queries/my_first_signal.json`
2. **Copy example**: Start with Example 1 above, modify for your data
3. **Set `enabled: false`** initially
4. **Add to git**: `git add queries/my_first_signal.json`
5. **Test locally**:
   - Restart service
   - Check `/queries` endpoint
   - Monitor logs for errors
6. **Test query**: Run SQL query manually against external database
7. **Set `enabled: true`** when confident
8. **Commit & PR**

## Questions?

- Review examples above
- Check [SPEC.md](../SPEC.md) for detailed architecture
- See [README.md](../README.md) for API documentation
- Check [CONTRIBUTING.md](../CONTRIBUTING.md) for development guidelines

---

**Last Updated**: 2026-08-10
