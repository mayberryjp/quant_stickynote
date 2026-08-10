# Quant Sticky Note - Project Specification

**Project Purpose**: A Python backend service that continuously discovers potential stock trading opportunities by executing configurable SQL queries against external databases, storing flagged symbols with trigger reasons and recommended buy prices in a persistent "sticky note" table.

**Status**: Specification Document  
**Version**: 1.0  
**Date**: 2026-08-10

---

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Technical Stack](#technical-stack)
4. [Database Schema](#database-schema)
5. [Configuration](#configuration)
6. [Progressive Development Slices](#progressive-development-slices)
7. [Coding Standards Reference](#coding-standards-reference)

---

## Overview

### Purpose & Goals
- **Primary Goal**: Read data from configured external SQL databases, execute pattern detection queries, and populate a local "sticky note" table with trading signals
- **User**: Traders/analysts reviewing flagged symbols for potential trade execution
- **Scope**: Backend service only - no web UI, REST API for querying stored signals
- **Operational Model**: Long-running daemon with scheduled trigger times, persistent storage, and graceful shutdown handling

### Core Entities
1. **Sticky Note** (main output):
   - `symbol` (VARCHAR 10): Stock ticker symbol
   - `trigger_reason` (TEXT): Name/description of the query/rule that generated this signal
   - `buy_price` (NUMERIC): Recommended entry price
   - `position_type` (VARCHAR 10): Direction of trade - `LONG` (buy/bull) or `SHORT` (sell/bear)
   - `created_at` (TIMESTAMP): When the signal was generated
   - `source_query_id` (VARCHAR 50): Reference to the query configuration that produced this signal
   - `status` (VARCHAR 20): `active`, `reviewed`, `cancelled`, `executed`
   - `notes` (TEXT, nullable): Manual notes from trader

2. **Query Definition** (configuration):
   - Stored as JSON in `queries/` directory
   - Defines: source database connection, SQL query, signal extraction rules, filtering

### Key Features
- **Modular Query Engine**: New queries added via JSON config files, no code changes required
- **Multi-source Support**: Query different external databases (data warehouses, APIs converted to SQL)
- **Scheduled Execution**: Configurable run times (e.g., daily at 9:30 AM, hourly scans)
- **Persistent & Resilient**: Local PostgreSQL storage, idempotent processing, duplicate detection
- **Observability**: Structured logging, health endpoints, Alembic version tracking

---

## Architecture

### High-Level Flow
```
[Start Service] 
    ↓
[Initialize Config & DB]
    ↓
[Load Query Definitions from JSON]
    ↓
[Main Loop]
    ├─ Check if trigger time reached
    ├─ For each enabled query:
    │   ├─ Connect to source database
    │   ├─ Execute SQL query
    │   ├─ Extract signals from result set
    │   ├─ Check for duplicates (symbol + reason combo)
    │   └─ Insert/Update sticky notes
    ├─ Sleep for configured interval (e.g., 60 seconds)
    └─ Repeat until shutdown signal
```

### Component Structure
```
quant_stickynote/
├── src/
│   └── quant_stickynote/
│       ├── __init__.py
│       ├── main.py                 # Entry point
│       ├── config.py               # Pydantic settings
│       ├── database.py             # SQLAlchemy setup, session management
│       ├── models.py               # SQLAlchemy ORM models
│       ├── api.py                  # Bottle app (health, ready, query endpoints)
│       ├── worker.py               # Main daemon loop
│       ├── query_engine.py         # Query execution and signal extraction
│       ├── signal_processor.py     # Deduplication, status management
│       ├── logger.py               # Structured logging
│       └── exceptions.py           # Custom exception hierarchy
├── alembic/                        # Database migrations
│   ├── versions/                   # Individual migration files
│   ├── env.py
│   └── alembic.ini
├── queries/                        # Query definitions (JSON)
│   ├── example_momentum.json
│   ├── example_rsi_oversold.json
│   └── README.md
├── supervisord/                    # Process management
│   ├── supervisord.conf
│   └── conf.d/
│       └── quant_stickynote.conf
├── Dockerfile
├── requirements.txt
├── setup.py
├── pytest.ini
├── tests/
│   ├── unit/
│   └── integration/
├── SPEC.md                         # This file
└── README.md
```

---

## Technical Stack

### Core Dependencies
| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Runtime** | Python | 3.12+ | Base language |
| **Web Server** | Bottle + Waitress | latest | Health/Ready/Query endpoints (20 workers) |
| **ORM** | SQLAlchemy | 2.0+ core only | No async, use core API with psycopg[binary] |
| **Database Drivers** | psycopg[binary] | 3.1+ | PostgreSQL (local + external) |
| **Migrations** | Alembic | 1.12+ | Schema versioning |
| **Config** | Pydantic + pydantic-settings | 2.7+ | Type-safe configuration from environment |
| **Logging** | Python `logging` + JSON | stdlib | Structured logs for ELK/CloudWatch |
| **Testing** | pytest + webtest | 7.4+ | Unit & integration tests |
| **Process Mgmt** | supervisord | 4.2+ | Daemon lifecycle management |
| **Packaging** | pip + setuptools | latest | Dependency management |

### External Dependencies (Optional)
- **Redis**: For caching external query results or dedup-key storage (future enhancement)
- **APScheduler**: For more sophisticated scheduling (if cron-like triggers needed)

---

## Database Schema

### Local Database (PostgreSQL)

#### Table: `sticky_notes`
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
CREATE INDEX idx_sticky_notes_symbol ON sticky_notes(symbol);
CREATE INDEX idx_sticky_notes_created_at ON sticky_notes(created_at DESC);
CREATE INDEX idx_sticky_notes_status ON sticky_notes(status);
CREATE INDEX idx_sticky_notes_position_type ON sticky_notes(position_type);
```

#### Table: `query_executions` (audit log)
```sql
CREATE TABLE query_executions (
    id BIGSERIAL PRIMARY KEY,
    query_id VARCHAR(50) NOT NULL,
    executed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    row_count INT,
    signals_extracted INT,
    duration_ms INT,
    status VARCHAR(20) NOT NULL CHECK (status IN ('success', 'error', 'skipped')),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_query_executions_query_id ON query_executions(query_id, executed_at DESC);
```

#### Table: `alembic_version`
```sql
CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
```

---

## Configuration

### Environment Variables (via Pydantic Settings)
```
# Service
SERVICE_NAME=quant_stickynote
ENVIRONMENT=production|development|test
LOG_LEVEL=DEBUG|INFO|WARNING|ERROR
LOG_FORMAT=json|text

# Database (Local)
DATABASE_URL=postgresql://user:pass@localhost:5432/quant_stickynote

# External Data Sources (Optional Global)
EXTERNAL_DB_POOL_SIZE=5
EXTERNAL_DB_POOL_RECYCLE=3600
EXTERNAL_DB_ECHO=false

# Scheduling
TRIGGER_TIME=09:30  # HH:MM format (UTC)
CHECK_INTERVAL_SECONDS=60
QUERY_TIMEOUT_SECONDS=300

# API Server
API_HOST=0.0.0.0
API_PORT=8080
API_WORKERS=20

# Worker Process
WORKER_ENABLED=true
WORKER_LOG_EVERY_N_CYCLES=10
```

### Query Configuration (JSON Format)

**File**: `queries/example_momentum.json`
```json
{
  "id": "momentum_breakout_001",
  "name": "Momentum Breakout Scanner",
  "description": "Finds stocks with increasing momentum",
  "enabled": true,
  "external_database": {
    "url": "postgresql://user:pass@data-warehouse:5432/market_data",
    "pool_size": 5,
    "pool_recycle": 3600
  },
  "source_query": "SELECT symbol, price, momentum_score FROM signals WHERE momentum_score > 0.75 AND updated_at > NOW() - INTERVAL '1 day'",
  "signal_extraction": {
    "symbol_column": "symbol",
    "buy_price_column": "price",
    "filter_expression": "momentum_score > 0.75"
  },
  "dedup_key_ttl_hours": 24,
  "max_results_per_run": 50
}
```

**File**: `queries/rsi_oversold.json`
```json
{
  "id": "rsi_oversold_002",
  "name": "RSI Oversold Reversal",
  "description": "RSI < 30 with reversal candlestick",
  "enabled": true,
  "external_database": {
    "url": "postgresql://user:pass@data-warehouse:5432/technical_analysis"
  },
  "source_query": "SELECT symbol, reversal_price as entry_price FROM oversold_reversals WHERE rsi < 30 AND DATE(scan_date) = CURRENT_DATE",
  "signal_extraction": {
    "symbol_column": "symbol",
    "buy_price_column": "entry_price",
    "filter_expression": null
  },
  "dedup_key_ttl_hours": 48
}
```

---

## Progressive Development Slices

Each slice is a self-contained, deliverable milestone. Subsequent slices depend on prior ones.

### **SLICE 1: Project Setup & Core Infrastructure** ⏱️ ~2-3 days
**Objective**: Establish project structure, database connectivity, and health endpoints

**Tasks**:
- [ ] Initialize project: `setup.py`, `requirements.txt`, `pyproject.toml`
- [ ] Create `src/quant_stickynote/` package structure
- [ ] Implement Pydantic settings (`config.py`) - load from environment variables
- [ ] Configure SQLAlchemy 2.0 core with psycopg[binary]
  - Database initialization
  - Connection pooling (pre_ping=True)
  - Session factory
- [ ] Create SQLAlchemy ORM models in `models.py`
  - `StickyNote` model
  - `QueryExecution` model
- [ ] Setup Alembic
  - Initialize migration environment
  - Create initial migration for `sticky_notes` and `query_executions` tables
- [ ] Implement `database.py` module
  - `get_session()` context manager
  - Schema version check
  - Retry logic for transient failures
- [ ] Create Bottle API (`api.py`)
  - `GET /health` → `{"status": "ok", "service": "quant_stickynote"}`
  - `GET /ready` → includes DB and schema version
- [ ] Create entry point (`main.py`)
  - Argument parsing (--api-only, --worker-only, --both)
  - Log initialization
- [ ] Create `logger.py`
  - JSON structured logging with service context
  - Timestamp, level, message, traceback fields
- [ ] Create Docker setup
  - Dockerfile (python:3.12-slim base)
  - `.dockerignore`
- [ ] Create `pytest.ini` and basic test harness
- [ ] Create `README.md` with setup instructions

**Acceptance Criteria**:
- Service starts without errors
- `GET /health` returns 200 OK
- `GET /ready` returns 200 OK and includes schema_version
- Alembic can run forward/backward
- All imports work correctly
- Tests run successfully (even if minimal)

**Dependencies**: None (first slice)

---

### **SLICE 2: Query Execution Engine** ⏱️ ~3-4 days
**Objective**: Build the core logic to load, execute, and extract signals from external databases

**Tasks**:
- [ ] Create `query_engine.py` module
  - `QueryDefinition` dataclass (Pydantic model)
  - `load_queries_from_directory()` - scan `queries/` folder for JSON files
  - Validate query definitions against schema
  - `execute_external_query()` - connect to external DB, run SQL, fetch results
  - `extract_signals()` - parse result rows into signal objects
  - Error handling & retry logic for external DB failures
- [ ] Implement connection pooling for external databases
  - Per-query external DB URL support
  - Reusable connection pools with configurable size/recycle
- [ ] Create signal extraction logic
  - Map result columns to symbol, buy_price, trigger_reason
  - Support templated trigger_reason (e.g., "RSI Oversold [RSI={rsi_value}]")
  - Filter rows based on filter expressions (or pure Python predicates)
- [ ] Create `signal_processor.py` module
  - `detect_duplicates()` - check if symbol + reason already exists today (UNIQUE constraint)
  - `insert_or_update_sticky_note()` - upsert logic with conflict handling
  - Track signal age and TTL
- [ ] Create custom exceptions (`exceptions.py`)
  - `DatabaseConnectionError`
  - `QueryExecutionError`
  - `SignalExtractionError`
  - `ConfigurationError`
- [ ] Add comprehensive unit tests
  - Mock external database queries
  - Test signal extraction with various result shapes
  - Test deduplication logic
  - Test error scenarios (connection failures, timeout, malformed results)
- [ ] Create example query definitions
  - Save to `queries/` directory
  - Document format and required fields

**Acceptance Criteria**:
- Load queries from JSON without errors
- Execute sample queries against mock database
- Extract signals correctly
- Deduplication works (no duplicate insertions same day)
- Error logging is clear and actionable
- Unit test coverage >80%

**Dependencies**: SLICE 1 (database models, config, logging)

---

### **SLICE 3: Worker Daemon & Scheduling** ⏱️ ~2-3 days
**Objective**: Implement the persistent, scheduled execution loop

**Tasks**:
- [ ] Create `worker.py` module
  - Main event loop logic
  - Check if current time >= trigger time
  - Execute all enabled queries in sequence
  - Record execution results to `query_executions` table
  - Handle graceful shutdown (SIGTERM, SIGINT)
  - Implement configurable sleep interval between checks
- [ ] Implement scheduling mechanism
  - Time-based trigger (e.g., "09:30" UTC daily)
  - Configurable check interval (every 60 seconds)
  - Avoid re-executing same query within window (use `query_executions` timestamp)
- [ ] Add state management
  - Track last execution time per query
  - Prevent duplicate runs within configured interval
  - Log execution summary every N cycles (configurable)
- [ ] Implement error recovery
  - Catch and log exceptions without crashing service
  - Continue to next query on failure
  - Exponential backoff for transient failures (optional)
- [ ] Create supervisord configuration
  - `supervisord/supervisord.conf` - main config
  - `supervisord/conf.d/quant_stickynote.conf` - service definition
  - autostart=true, autorestart=true, redirect_stderr=true
  - Define stdout_logfile for worker process
- [ ] Update `main.py` to support modes
  - `--api-only` - run only health/ready endpoints
  - `--worker-only` - run only the daemon loop
  - `--both` - run both (default)
- [ ] Add integration tests
  - Test full worker cycle with mock external DB
  - Verify signal insertion after execution
  - Test graceful shutdown handling
- [ ] Create `queries/README.md`
  - Document JSON schema for query definitions
  - Provide example queries with comments
  - Explain signal extraction and dedup behavior

**Acceptance Criteria**:
- Worker starts and runs scheduled checks
- Executes queries at configured trigger time
- Inserts signals to sticky_notes table
- Logs execution metadata to query_executions
- Handles errors gracefully without crashing
- Responds to SIGTERM for clean shutdown
- supervisord can start/stop service reliably
- No signals inserted twice in same day

**Dependencies**: SLICE 2 (query engine), SLICE 1 (infrastructure)

---

### **SLICE 4: REST API & Query Interface** ⏱️ ~2-3 days
**Objective**: Expose sticky notes and metadata via REST API

**Tasks**:
- [ ] Extend `api.py` with REST endpoints
  - `GET /sticky-notes` - list all active notes (with pagination)
    - Query params: `limit`, `offset`, `symbol`, `status`
    - Returns JSON array with proper schema
  - `GET /sticky-notes/{id}` - get single note details
  - `POST /sticky-notes/{id}/status` - update note status (trader actions)
    - Accept `status` in request body
    - Only allow valid state transitions
  - `GET /queries` - list all loaded query definitions
  - `GET /queries/{id}/executions` - query execution history
    - Query params: `limit`, `offset`, `date_from`, `date_to`
  - `GET /queries/{id}/last-execution` - status of last run
- [ ] Implement error responses
  - Standardized error schema: `{"error": "message", "code": "ERROR_CODE"}`
  - Appropriate HTTP status codes
  - No sensitive DB details in responses
- [ ] Add request validation
  - Validate query parameters and request bodies
  - Return 400 Bad Request with clear messages
- [ ] Implement pagination
  - Support limit/offset pattern
  - Include total_count in response
- [ ] Add unit tests for all endpoints
  - Mock database queries
  - Test happy paths and error cases
  - Test pagination
- [ ] Create API documentation
  - OpenAPI/Swagger schema (optional, can be simple docs)
  - Example requests and responses
- [ ] Extend supervisord config
  - Separate process for API server vs worker (or keep combined)
  - Document how to scale API independently

**Acceptance Criteria**:
- All endpoints return correct status codes
- JSON schema is consistent and documented
- Pagination works correctly
- Status updates persist to database
- Tests pass with >80% coverage
- API can be queried while worker is running
- No errors in logs for valid requests

**Dependencies**: SLICE 1-3 (all prior slices)

---

### **SLICE 5: Monitoring, Metrics & Observability** ⏱️ ~2-3 days
**Objective**: Add detailed logging, metrics, and operational dashboards

**Tasks**:
- [ ] Enhance structured logging
  - Add context fields (query_id, symbol, signal_count, duration)
  - Log all external DB connections, queries, and results
  - Log error traces with full context
  - Ensure all logs are JSON-serializable
- [ ] Create metrics collection
  - Count signals extracted per query
  - Track query execution times
  - Monitor external DB connection failures
  - Track duplicate signal detection
- [ ] Add health check enhancements
  - Include signal count (24h, 7d)
  - Report last query execution time per query_id
  - Include uptime
- [ ] Implement graceful degradation
  - Service stays healthy even if one external DB is unavailable
  - Log failed queries but continue processing others
- [ ] Create debugging/diagnostics endpoint
  - `GET /debug/config` - current config (non-sensitive)
  - `GET /debug/queries` - loaded query status
  - `GET /debug/stats` - runtime statistics
  - (Optional: require authentication)
- [ ] Document logging format
  - Example log entries
  - Expected fields
  - How to search/filter in ELK or CloudWatch
- [ ] Create operational runbook
  - How to add new queries
  - How to restart worker
  - How to investigate failures
  - Common issues and solutions
- [ ] Load testing (basic)
  - Verify API handles concurrent requests
  - Verify worker doesn't leak connections

**Acceptance Criteria**:
- All logs are structured JSON
- Metrics are easily queryable
- Health endpoint includes useful diagnostics
- Runbook is clear and complete
- Performance is acceptable under load
- No connection leaks or resource issues

**Dependencies**: SLICE 1-4 (all prior slices)

---

### **SLICE 6: Deployment & DevOps** ⏱️ ~2 days
**Objective**: Package for production deployment

**Tasks**:
- [ ] Create Dockerfile
  - Multi-stage build (optional)
  - Minimal final image (python:3.12-slim)
  - Non-root user execution
  - Health check defined
- [ ] Create docker-compose.yml (local dev)
  - PostgreSQL service
  - quant_stickynote service
  - Volume mounts for code and queries
- [ ] Create Kubernetes manifests (optional)
  - Deployment
  - Service
  - ConfigMap for environment variables
  - Secrets for database credentials
- [ ] Create CI/CD pipeline (GitHub Actions or similar)
  - Lint (flake8, black)
  - Test (pytest)
  - Build Docker image
  - Push to registry
- [ ] Document deployment process
  - Prerequisites (Python 3.12, PostgreSQL)
  - Environment setup
  - Database initialization
  - supervisord startup
  - Monitoring and log aggregation setup
- [ ] Create migration runbook
  - How to run Alembic migrations in production
  - Rollback procedure
  - Zero-downtime deployment strategy
- [ ] Setup configuration management
  - Environment-specific configs
  - Secrets management (avoid hardcoding)

**Acceptance Criteria**:
- Docker image builds successfully
- Service runs in Docker with database
- CI/CD pipeline passes all stages
- Deployment documentation is complete
- Can be deployed to production with confidence

**Dependencies**: SLICE 1-5 (all prior slices)

---

### **SLICE 7: Testing & Documentation** ⏱️ ~2 days
**Objective**: Comprehensive test coverage and user/developer documentation

**Tasks**:
- [ ] Expand test suite
  - Unit tests for all modules (target 80%+ coverage)
  - Integration tests with real SQLite (or test PostgreSQL)
  - End-to-end tests with mock external DB
  - Error scenario tests
- [ ] Create test data and fixtures
  - Sample query definitions
  - Sample external DB result sets
  - Sample sticky notes for assertions
- [ ] Add performance tests
  - Measure query execution times
  - Measure deduplication performance
  - Load testing scenarios
- [ ] Create comprehensive README.md
  - Project overview
  - Quick start guide
  - Architecture explanation
  - Query definition guide
  - API documentation
  - Troubleshooting section
- [ ] Create CONTRIBUTING.md
  - Development setup
  - Running tests locally
  - Code style guidelines
  - Pull request process
- [ ] Add inline code documentation
  - Docstrings for all public functions
  - Comments for complex logic
  - Type hints throughout
- [ ] Create CHANGELOG.md
  - Version history
  - Known issues
  - Upgrade path

**Acceptance Criteria**:
- Test coverage >80%
- All tests pass
- Documentation is complete and accurate
- Any developer can set up and run project locally
- Code is well-commented and clear

**Dependencies**: SLICE 1-6 (all prior slices)

---

### **SLICE 8: Advanced Features (Optional)** ⏱️ ~3+ days
**Objective**: Add optional enhancements for robustness and extensibility

**Tasks**:
- [ ] Implement caching layer
  - Redis cache for external query results (reduce load on external DBs)
  - Configurable TTL per query
  - Cache invalidation strategy
- [ ] Add signal correlation/denoising
  - If same symbol triggered by multiple queries in short window, merge and note all triggers
  - Implement signal scoring/ranking
  - Reduce noise for traders
- [ ] Implement email/webhook notifications
  - Alert traders when new signals arrive
  - Configurable rules (only certain symbols, thresholds, etc.)
  - Retry logic for failed notifications
- [ ] Add audit logging
  - Track all status changes to sticky notes
  - Who changed it, when, why
  - Immutable audit log
- [ ] Advanced scheduling
  - Support multiple trigger times per query (e.g., 09:30 and 14:30)
  - Cron-like scheduling via APScheduler
  - One-time vs recurring queries
- [ ] Add multi-tenancy support
  - Different traders/teams can have isolated signal views
  - Configurable access control
- [ ] Implement signal backtesting
  - Store historical signals and outcomes
  - Evaluate query performance
  - Help tune and improve queries
- [ ] Create admin UI
  - Web dashboard for status, metrics, query management
  - (Note: separate frontend project)

**Acceptance Criteria** (varies by feature):
- Depends on selected features
- Should maintain backward compatibility
- Comprehensive tests for new features
- Documentation for new functionality

**Dependencies**: SLICE 1-7 (all prior slices)

---

## Coding Standards Reference

### Python Standards (per quant repos)
1. **Version**: Python 3.12 minimum
2. **Imports**: Standard library → third-party → local, one per line (or groups)
3. **Type Hints**: All public function signatures must include type hints
4. **Docstrings**: Google style for modules, classes, functions
5. **Error Handling**: Specific exception types, never bare `except:`
6. **Logging**: Use `logging` module with structured JSON context
7. **Database**: SQLAlchemy 2.0 core API (not ORM for queries), psycopg[binary]
8. **Migrations**: Alembic required for all schema changes
9. **Configuration**: Pydantic Settings from environment variables
10. **Testing**: pytest with fixtures, mocking external dependencies
11. **Code Style**: Black formatter, flake8 linter, isort for imports

### Project Organization Standards
- `src/<package_name>/` for source code
- `tests/` with `unit/` and `integration/` subdirectories
- `alembic/` for migrations (generated by Alembic init)
- Configuration files at root level
- Docker and deployment configs in dedicated folders
- Query definitions in `queries/` directory

### API Standards (Bottle/Waitress)
- Health check at `GET /health`
- Readiness check at `GET /ready` (includes DB connectivity and schema_version)
- Errors use standardized JSON: `{"error": "message", "code": "CODE"}`
- 20 Waitress worker threads
- All responses are JSON (except logs)
- Query params for filtering, POST body for mutations

### Database Standards
- Use connection pooling: `pool_pre_ping=True`
- All tables have `created_at` and `updated_at` timestamps
- Use UNIQUE constraints for deduplication
- Use indexes for query columns (symbol, status, created_at)
- Alembic migrations for all schema changes
- Never use raw SQL in application code (use ORM or core API)

### Logging Standards
- Structured JSON format with: timestamp, level, service, message, context
- Include relevant IDs (query_id, symbol, etc.) in context
- Log external DB operations (connect, query, result count)
- Log errors with full traceback
- Do NOT log sensitive data (passwords, full connection strings)

---

## Implementation Notes for Backend Engineers

### Recommended Reading Order
1. This spec (SPEC.md)
2. Reference repo: `quant_daily_bars` (data ingestion pattern)
3. Reference repo: `quant_signals` (query execution and dedup pattern)
4. Reference repo: `quant_momentum` (Bottle/API pattern)
5. Backend Coding Standards: https://github.com/mayberryjp/coding_standards/blob/main/BACKEND_CODING_STANDARDS.md

### Key Implementation Considerations
- **External Database Connections**: Never hardcode URLs; use Pydantic config and query-level overrides
- **Query Execution Safety**: Timeout all external queries (300s default), catch and log all errors
- **Deduplication**: Use (symbol, trigger_reason, date) as natural key; check before every insert
- **Idempotency**: If worker is restarted mid-execution, don't insert duplicate signals
- **Gradual Rollout**: Start with 1-2 test queries, add more as confidence grows
- **Monitoring**: Log every signal extracted; make it queryable for auditing
- **Backward Compatibility**: New query features shouldn't break existing queries

### Testing Strategy
- Unit test each module in isolation (mock external dependencies)
- Integration tests with real local PostgreSQL (docker-compose)
- End-to-end tests simulating full worker cycle
- Always include happy path + error scenario tests

### Performance Targets
- Query execution: <5 seconds for most queries (config timeout 300s)
- Dedup check: <100ms
- Insert 1000 signals: <2 seconds
- API response: <500ms for 99th percentile
- Memory: <500MB steady state
- Startup time: <5 seconds

---

## Success Criteria (Overall Project)

✅ **MVP Complete** when:
1. Service starts and runs scheduled checks (SLICE 3)
2. Executes external queries and inserts signals (SLICE 2-3)
3. API responds to status queries (SLICE 4)
4. No duplicate signals inserted same day (SLICE 2-3)
5. Gracefully handles external DB failures (SLICE 3)
6. Structured logging is operational (SLICE 5)
7. Deployed and running via Docker + supervisord (SLICE 6)

✅ **Production Ready** when:
- All SLICE 1-6 complete
- Test coverage >80%
- Documentation complete
- Monitoring/alerting configured
- First 2 queries successfully running
- Trader feedback collected and issues resolved

---

## Appendix: Query Definition JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Quant Sticky Note Query Definition",
  "type": "object",
  "required": [
    "id",
    "name",
    "description",
    "external_database",
    "source_query",
    "signal_extraction"
  ],
  "properties": {
    "id": {
      "type": "string",
      "description": "Unique identifier for this query (alphanumeric + underscores)"
    },
    "name": {
      "type": "string",
      "description": "Human-readable query name"
    },
    "description": {
      "type": "string",
      "description": "What this query looks for and why"
    },
    "enabled": {
      "type": "boolean",
      "default": true,
      "description": "Whether to execute this query in scheduled runs"
    },
    "external_database": {
      "type": "object",
      "required": ["url"],
      "properties": {
        "url": {
          "type": "string",
          "description": "PostgreSQL connection URL (can include env var like $EXTERNAL_DB_URL)"
        },
        "pool_size": {
          "type": "integer",
          "default": 5,
          "description": "SQLAlchemy connection pool size"
        },
        "pool_recycle": {
          "type": "integer",
          "default": 3600,
          "description": "Connection recycle time in seconds"
        },
        "query_timeout": {
          "type": "integer",
          "default": 300,
          "description": "Query timeout in seconds"
        }
      }
    },
    "source_query": {
      "type": "string",
      "description": "SQL SELECT query to execute against external database"
    },
    "signal_extraction": {
      "type": "object",
      "required": ["symbol_column", "buy_price_column"],
      "properties": {
        "symbol_column": {
          "type": "string",
          "description": "Result column name containing stock symbol"
        },
        "buy_price_column": {
          "type": "string",
          "description": "Result column name containing recommended buy price"
        },
        "trigger_reason_template": {
          "type": "string",
          "description": "Template for trigger_reason (e.g., 'RSI Oversold [value={rsi}]'). If omitted, uses query name."
        },
        "filter_expression": {
          "type": ["string", "null"],
          "description": "Optional Python expression to filter rows (e.g., 'score > 0.8')"
        }
      }
    },
    "dedup_key_ttl_hours": {
      "type": "integer",
      "default": 24,
      "description": "How long (in hours) to consider a symbol + trigger_reason as duplicate if already in DB"
    },
    "max_results_per_run": {
      "type": "integer",
      "default": 50,
      "description": "Maximum number of signals to insert from this query per run"
    }
  }
}
```

---

**End of Specification**

For questions or clarifications, contact the project lead or refer to the Coding Standards guide.
