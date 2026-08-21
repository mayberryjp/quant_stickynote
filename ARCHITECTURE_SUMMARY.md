# Quant Stack Architecture Summary

## Overview
The quantitative trading stack consists of three interconnected services:
1. **quant_momentum** - Database & migrations framework
2. **quant_signals** - Signal cache & watchlist service  
3. **quant_daily_bars** - Daily bar ingestion from Polygon

---

## 1. quant_momentum
**Purpose**: Database infrastructure and schema management

### Tech Stack
- **Database**: PostgreSQL (psycopg)
- **ORM**: SQLAlchemy
- **Migrations**: Alembic
- **Version**: 0.1.0

### Key Components
- **db.py**: Database engine factory with connection pooling

  - `get_engine()` - SQLAlchemy engine with pool_pre_ping=True
  - `make_alembic_config()` - builds migration configuration
  - `upgrade()` - applies migrations to head

- **Alembic Setup**
  - `alembic.ini` - configuration file
  - `alembic/env.py` - runtime configuration
  - `alembic/script.py.mako` - migration template
  - Version table: `momentum.alembic_version_momentum`

### Configuration
```
DATABASE_URL = postgresql+psycopg://quant:quant_dev_password@localhost:5432/quant
```

### CLI Commands
```bash
poetry run python -m quant_momentum.cli db upgrade
poetry run python -m quant_momentum.cli db verify
```

---

## 2. quant_signals
**Purpose**: Redis-backed signal cache with watchlist management and Postgres archival

### Tech Stack
- **Cache**: Redis (runtime)
- **Persistence**: PostgreSQL (optional archival)
- **API**: Bottle (WSGI)
- **Tests**: pytest + WebTest + fakeredis
- **Port**: 8016 (default)

### Architecture Tiers

#### Tier 1: Redis Contracts (redis/keys.py)
Redis key namespace: `qs:` (quant-signals)

**Primary Keys**:
- `qs:source:<name>` → SignalSource JSON (TTL: 30d)
- `qs:idem:<source>:<key>` → IdempotencyRecord JSON (TTL: 24h)
- `qs:signal:<source>:<key>` → SignalCacheRecord JSON (TTL: 7d)
- `qs:watchlist:<source>:<type>:<ticker>` → WatchlistEntry JSON (TTL: 30d)

**Secondary Indexes**:
- `qs:idx:signals:recent` - sorted set (score = received_at epoch)
- `qs:idx:watchlist:active` - set of active entry IDs
- `qs:idx:watchlist:source:<source>` - entries by source
- `qs:idx:watchlist:ticker:<TICKER>` - entries by ticker (uppercase)
- `qs:idx:watchlist:market:<market>` - entries by market
- `qs:idx:watchlist:locale:<locale>` - entries by locale
- `qs:idx:watchlist:signal_type:<type>` - entries by signal type
- `qs:idx:watchlist:tag:<tag>` - entries by tag

**Counters**:
- `qs:counter:accepted` - accepted signals
- `qs:counter:duplicate` - duplicate submissions
- `qs:counter:rejected` - rejected signals
- `qs:counter:unresolved` - unresolved tickers
- `qs:counter:failed` - failed ingestions
- `qs:counter:expired` - expired records
- `qs:counter:watchlist_upserts` - watchlist updates

#### Tier 2: Data Models (models/domain.py)
```
SignalStatus = {accepted, duplicate, rejected, unresolved, failed, expired, superseded}
WatchlistStatus = {active, inactive, expired}
SignalDirection = {long, short, neutral}

SignalSource
  - name: str
  - source_type: str
  - enabled: bool
  - created_at, updated_at: datetime
  - schema_version: int

SignalCacheRecord
  - signal_cache_id: str  # Format: signal:<source>:<key>
  - source, idempotency_key: str
  - submitted_ticker, canonical_ticker: str
  - symbol_id: int | None
  - market, locale, signal_type: str
  - direction, score, confidence, horizon: Optional
  - reason: str
  - tags: list[str]
  - metadata: dict[str, Any]
  - status, rejection_reason: str | None
  - received_at, processed_at: datetime
  - watchlist_entry_id: str | None
  - schema_version: int

WatchlistEntry
  - watchlist_entry_id: str  # Format: watchlist:<source>:<type>:<TICKER>
  - source, signal_type, submitted_ticker: str
  - canonical_ticker, symbol_id: Optional
  - market, locale: str
  - status, direction, score, confidence, horizon: ...
  - reason, tags, metadata: ...
  - Lineage: latest/first/last_seen_signal_cache_id, seen_count
  - created_at, updated_at, created_by: ...
  - schema_version: int
```

#### Tier 3: Repository Layer (redis/repository.py)
`SignalCacheRepository` - encapsulates all Redis operations

**Signal Operations**:
- `store_signal()` - persist with TTL, index by received_at
- `get_signal()` - by source + idempotency_key
- `get_signal_by_id()` - by signal_cache_id
- `get_recent_signals()` - sorted by timestamp

**Idempotency**:
- `check_idempotency()` - guard against duplicates
- `set_idempotency()` - record duplicate key with TTL

**Watchlist Operations**:
- `upsert_watchlist_entry()` - create or merge entry, update indexes
- `get_watchlist_entry()` - by source + type + ticker
- `get_watchlist_entry_by_id()` - by entry_id
- `deactivate_watchlist_entry()` - mark as inactive
- `patch_watchlist_entry()` - partial updates
- `list_watchlist()` - filtered query with pagination

**Counters & Maintenance**:
- `get_counters()` - fetch all counter values
- `get_active_watchlist_count()` - cardinality
- `get_heartbeat()`, `set_heartbeat()` - maintenance scheduling
- `prune_recent_signals()` - cleanup expired entries

#### Tier 4: API Routes (routes/)

**health.py** (Slice 7)
- `GET /signal-cache/health` → `{"status": "ok"}`
- `GET /signal-cache/ready` → readiness + Redis status
- `GET /signal-cache/stats` → counters + active count + maintenance heartbeat

**signals.py** (Slice 2 - Signal Intake)
- `POST /signals` - submit signal, return 201 with signal_cache_id + watchlist_entry_id
  - Validation: source, ticker, reason, score/confidence ranges
  - Idempotency check
  - Symbol resolution
  - Watchlist upsert
  - Postgres archival (best-effort)
- `GET /signals/recent?limit=50` - recent signals by timestamp
- `GET /signals/<signal_cache_id>` - signal detail

**watchlist.py** (Slice 4 - Watchlist Read, Slice 5 - Write)
- `GET /watchlist?source=...&ticker=...&market=...&locale=...&tag=...&signal_type=...&page=...&page_size=...` 
  - Paginated list with multi-dimensional filters
  - Index intersection via Redis SINTERSTORE
- `GET /watchlist/<watchlist_entry_id>` - entry detail
- `GET /watchlist/by-ticker/<ticker>` - all entries for ticker
- `POST /watchlist` - manual add
- `PATCH /watchlist/<id>` - update/deactivate

#### Tier 5: Signal Intake Service (services/signal_service.py)
`ingest_signal()` orchestration (9 steps):
1. Idempotency check (return duplicate if exists)
2. Ensure source exists (get_or_create)
3. Build signal_cache_id
4. Resolve symbol (stub backend or real)
5. Build signal record
6. Persist to Redis
7. Idempotency record with TTL
8. Upsert watchlist entry + seen metadata
9. Archive to Postgres (best-effort, never blocks)

**Symbol Resolution**:
- `SymbolResolver.resolve(ticker, market, locale)` → ResolvedSymbol
- Stub backend returns `None` if not found → status = unresolved
- Future: real backend queries symbol_master

#### Tier 6: Postgres Archive (repository/signal_archive.py)
Schema: `signal_cache.signal_archive`
- Append-only archive of all signals
- Idempotency via `ON CONFLICT (source, idempotency_key) DO NOTHING`
- Indexes: source, submitted_ticker, status, received_at, signal_type
- Called after Redis write (async, fire-and-forget)

### Request/Response Schemas

**SignalSubmission (POST /signals)**
```json
{
  "source": "momentum-v1",  // 1-128 chars, required
  "idempotency_key": "momentum-v1:2026-06-09:AAPL",  // 1-512 chars, required
  "ticker": "AAPL",  // 1-20 chars, required
  "market": "stocks",  // default: stocks
  "locale": "us",  // default: us
  "signal_type": "watchlist_candidate",  // default
  "direction": "long",  // long, short, neutral
  "score": 0.87,  // 0.0-1.0
  "confidence": 0.72,  // 0.0-1.0
  "horizon": "5d",  // max 32 chars
  "reason": "...",  // max 2000 chars, required
  "tags": ["momentum", "breakout"],  // max 20 items
  "metadata": {...}  // max 16 KB
}
```

**SignalAcceptedResponse (201)**
```json
{
  "status": "accepted|duplicate|unresolved",
  "signal_cache_id": "signal:momentum-v1:momentum-v1:2026-06-09:AAPL",
  "watchlist_status": "active",
  "watchlist_entry_id": "watchlist:momentum-v1:watchlist_candidate:AAPL"
}
```

**WatchlistListResponse (GET /watchlist)**
```json
{
  "items": [
    {
      "watchlist_entry_id": "watchlist:momentum-v1:watchlist_candidate:AAPL",
      "source": "momentum-v1",
      "signal_type": "watchlist_candidate",
      "submitted_ticker": "AAPL",
      "canonical_ticker": "AAPL",
      "symbol_id": 1,
      "market": "stocks",
      "locale": "us",
      "status": "active",
      "direction": "long",
      "score": 0.87,
      "confidence": 0.72,
      "horizon": "5d",
      "reason": "...",
      "tags": [...],
      "metadata": {...},
      "latest_signal_cache_id": "signal:...",
      "first_seen_signal_cache_id": "signal:...",
      "last_seen_signal_cache_id": "signal:...",
      "seen_count": 1,
      "created_at": "2026-06-09T...",
      "updated_at": "2026-06-09T...",
      "created_by": "momentum-v1"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 25
}
```

### Testing Infrastructure
- **conftest.py**: fakeredis fixture, app_client TestApp
- **test_slice1_redis_contracts.py**: Redis key patterns, serialization
- **test_slice2_signal_intake.py**: signal validation, idempotency, seen metadata
- **test_slice4_watchlist_read.py**: filtering, pagination
- **test_slice8_hardening.py**: boundary validation

### Known Limitations
- No Postgres pipeline or fanout system (Redis only)
- No Kafka/NATS/Redis Streams event bus
- No broker integration or trade execution
- No auth/permissions
- No frontend UI
- No external vendor calls during intake
- Symbol resolution is stub-only (unless real DB configured)

---

## 3. quant_daily_bars
**Purpose**: OHLCV bar ingestion from Polygon into Postgres

### Tech Stack
- **Vendor API**: Polygon.io (`/v2/aggs/ticker/{ticker}/range/1/day/{from}/{to}`)
- **Client**: Custom PolygonBarsClient with sliding-window rate limiter
- **Database**: PostgreSQL + Alembic migrations
- **API**: Bottle (WSGI)
- **Job Runner**: ThreadPoolExecutor (bounded async)
- **Port**: 8000 (default)

### Rate Limiting
- Free tier: 5 requests/minute
- Sliding-window enforced in client
- Automatic backoff on rate limit

### Database Schema
**market_data** schema:

| Table | Purpose |
|-------|---------|
| `vendor_bar_sources` | Registered vendors (seeded: polygon) |
| `vendor_bar_runs` | Per-run tracking (mode, dates, counts, duration) |
| `daily_bars` | OHLCV keyed by (symbol_id, bar_date, adjustment_type) |
| `corporate_actions` | Splits, dividends (placeholder) |
| `missing_bars` | Expected but not returned (for inspection) |

**daily_bars columns**:
- symbol_id, bar_date, adjustment_type (composite key)
- open, high, low, close, volume, vwap
- transactions (Polygon-specific)
- vendor_source_id, vendor_bar_run_id (lineage)
- fetched_at (UTC timestamp)

**Idempotent Upsert**:
```sql
INSERT INTO market_data.daily_bars (...)
ON CONFLICT (symbol_id, bar_date, adjustment_type) DO UPDATE SET
  open=EXCLUDED.open, high=EXCLUDED.high, ...
  vendor_bar_run_id=EXCLUDED.vendor_bar_run_id,
  fetched_at=EXCLUDED.fetched_at
```

### Ingest Job Orchestration (job.py)

**IngestOptions**:
```python
from_date: date
to_date: date
tickers: list[str] | None = None  # None = all active from symbol_master
adjustment_type: str = "unadjusted"  # or split_adjusted
mode: str = "backfill"  # or incremental
fixture_path: str | None = None
dry_run: bool = False
```

**DailyBarIngestJob.run(options)** (11 steps):
1. Validate inputs
2. Resolve symbol targets from symbol_master or tickers
3. Create vendor_bar_runs record (mode, dates, count)
4. For each target:
   - Fetch bars from Polygon (pagination)
   - Upsert into daily_bars
   - Increment bar counter
   - Heartbeat to prevent stale-run cleanup
   - Handle errors per-symbol (isolation)
5. Record missing bars for inspection
6. Finalize run (set counts, status)
7. Return IngestSummary

**IngestSummary**:
```python
mode: str
status: str = "ok" | "failed"
symbols_requested, symbols_succeeded, symbols_failed: int
bars_upserted: int
missing_bars_recorded: int
errors: int
duration_seconds: float
run_id: int | None
warnings: list[str]
failures: list[str]
```

### Async Job Runner (ingest_jobs.py)

**IngestJobManager** - thread pool + registry

States:
- `queued` → `running` → `completed` or `failed`

Operations:
- `submit(params)` → job_id (returns 202)
- `get(job_id)` → job detail
- `list_jobs(limit)` → recent jobs

Job Record:
```python
job_id: str
params: IngestTriggerParams
state: str
submitted_at, started_at, finished_at: str
run_id: int | None
summary: dict | None
error: str | None
```

**IngestTriggerParams**:
```python
from_date: date (required)
to_date: date (required)
tickers: list[str] | None = None
adjustment_type: str = "unadjusted"
mode: str = "backfill"
```

### API Routes (app.py)

**Health & Readiness**:
- `GET /health` → readiness check (DB, schema version, latest run)
- `GET /ready` → DB connectivity

**Bars Queries**:
- `GET /bars?ticker=AAPL&from_date=...&to_date=...&adjustment_type=...&limit=100&offset=0`
  - Paginated bar list
- `GET /bars/<ticker>/summary` → aggregated stats (date range, bar count, latest)
- `GET /bars/date-range` → min/max dates across all tickers
- `GET /bars/coverage` → tickers coverage summary

**Ingest Runs**:
- `GET /ingest/runs?status=...&mode=...&limit=20&offset=0` → run history
- `GET /ingest/runs/<run_id>` → run detail (symbols, bars, errors)
- `GET /ingest/latest` → latest run summary

**Ingest Trigger (Async)**:
- `POST /ingest` (202 Accepted)
  ```json
  {
    "from_date": "2024-01-03",
    "to_date": "2024-01-05",
    "tickers": ["MSFT", "AAPL"],
    "adjustment_type": "unadjusted",
    "mode": "backfill"
  }
  ```
  Returns:
  ```json
  {
    "status": "accepted",
    "job": {
      "job_id": "uuid",
      "state": "queued",
      "from_date": "2024-01-03",
      "to_date": "2024-01-05",
      "submitted_at": "ISO8601"
    }
  }
  ```

- `GET /ingest/jobs` → recent jobs
- `GET /ingest/jobs/<job_id>` → job detail with summary

**Missing Bars & Gap Analysis**:
- `GET /missing-bars?ticker=AAPL&limit=100&offset=0` → bars expected but not returned
- `GET /coverage-gaps?reference_ticker=MSFT&from_date=...&limit=1000` → date gaps by symbol
- `GET /gap-rankings/symbols` → which symbols have most gaps
- `GET /gap-rankings/dates` → which dates have most gaps
- `GET /backfill-progress?from_date=2025-06-01` → backfill completion %

### CLI Usage

```bash
# One-shot ingest
python -m quant_daily_bars.cli ingest \
  --from-date 2024-01-03 \
  --to-date 2024-01-05 \
  --tickers MSFT,AAPL \
  --adjustment-type unadjusted \
  --mode backfill

# Scheduled incremental (runs every N seconds)
python -m quant_daily_bars.cli ingest \
  --schedule 86400 \
  --tickers MSFT,AAPL

# Fixture-based dry-run (no API, no DB)
python -m quant_daily_bars.cli ingest \
  --fixture /path/to/fixture.json \
  --dry-run

# Verify database schema
python -m quant_daily_bars.cli db verify

# Apply migrations
python -m quant_daily_bars.cli db upgrade
```

---

## Data Flow Architecture

```
Signal Producers
       ↓
POST /signals (quant_signals)
       ↓
Redis: cache signal + watchlist
       ↓
Postgres: archive signal (best-effort)
       ↓
GET /watchlist → query active entries
       ↓
       └──────────────────────────┐
                                   ↓
                          Watchlist for trading
                                   ↓
                          GET /bars (quant_daily_bars)
                                   ↓
                    POST /ingest (async job)
                                   ↓
                    Polygon API (5req/min rate limit)
                                   ↓
                    Postgres: upsert daily_bars
                                   ↓
                    GET /bars queries
```

---

## Dependency Matrix

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| quant_signals | quant_momentum | Postgres schema, migration framework |
| quant_signals | Redis | Runtime cache (required) |
| quant_signals | Postgres (optional) | Historical archival |
| quant_daily_bars | quant_momentum | Postgres schema, migration framework |
| quant_daily_bars | Postgres | Market data storage |
| quant_daily_bars | Polygon API | OHLCV data source |
| Trading Logic | quant_signals | Watchlist (what to trade) |
| Trading Logic | quant_daily_bars | OHLCV bars (when to trade) |

---

## Configuration & Secrets

### quant_momentum
- `DATABASE_URL` (env) → PostgreSQL connection string

### quant_signals
- `DATABASE_URL` (env, optional) → Postgres for archival
- `REDIS_URL` (env, default: localhost:6379)
- `API_LISTEN_ADDRESS` (env, default: 0.0.0.0)
- `API_PORT` (env, default: 8016)

### quant_daily_bars
- `DATABASE_URL` (env) → PostgreSQL connection string (required)
- `POLYGON_API_KEY` (env) → Polygon.io API key
- `API_LISTEN_ADDRESS` (env, default: 0.0.0.0)
- `API_PORT` (env, default: 8000)

---

## Testing Strategy

| Service | Test Types | Tools |
|---------|-----------|-------|
| quant_momentum | Migration verification | Alembic, psycopg |
| quant_signals | Redis contracts, idempotency, validation | pytest, fakeredis, WebTest |
| quant_daily_bars | Fixture ingest, fixture dry-run, upsert SQL | pytest, JSON fixtures |

---

## Deployment Checklist

- [ ] Set `DATABASE_URL` for Postgres
- [ ] Initialize Postgres: `db upgrade`
- [ ] Verify schema: `db verify`
- [ ] For quant_signals: set up Redis, optional Postgres archival
- [ ] For quant_daily_bars: set `POLYGON_API_KEY`
- [ ] Start services on desired ports
- [ ] Test API endpoints with curl/Postman
- [ ] Monitor job runs and error logs

---

Generated: 2026-06-09
Last Updated: From quant_momentum, quant_signals, quant_daily_bars repos
