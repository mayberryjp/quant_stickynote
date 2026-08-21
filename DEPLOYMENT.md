# Production Deployment Guide

This guide covers the complete production deployment of the Quant Sticky Note service with supervisord, alembic migrations, and proper coding standards compliance.

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│          Docker Container (Python 3.12)             │
├─────────────────────────────────────────────────────┤
│                                                     │
│  alembic upgrade head                              │
│         ↓                                            │
│  supervisord -n (no-daemon mode)                   │
│         ↓                                            │
│  [program:worker]                                  │
│  → python -m quant_stickynote.worker              │
│     ↓                                               │
│     Worker.run() main loop                         │
│     → Poll every CHECK_INTERVAL_SECONDS           │
│     → Execute queries at TRIGGER_TIME             │
│     → Process signals & persist                    │
│                                                     │
└─────────────────────────────────────────────────────┘
         ↓
  External Data Warehouse
  (PostgreSQL with symbol/price tables)
```

## Deployment Steps

### Prerequisites

- Docker and Docker Compose installed
- Access to external data warehouse with PostgreSQL connection string
- Environment variables defined (see Configuration section)

### 1. Build the Docker Image

```bash
docker build -t quant-sticky-note:latest .
```

This will:
- Install Python 3.12 and dependencies
- Install supervisord and curl
- Copy application code (src/, alembic/)
- Create non-root user (appuser)
- Set up healthcheck endpoint

### 2. Configure Environment Variables

Create a `.env` file in the project root:

```bash
DATABASE_URL=postgresql://user:password@host:5432/database
TRIGGER_TIME=09:30
CHECK_INTERVAL_SECONDS=60
LOG_LEVEL=INFO
```

**Required Variables:**
- `DATABASE_URL`: PostgreSQL connection string to data warehouse

**Optional Variables:**
- `TRIGGER_TIME`: UTC time to execute queries (default: 09:30)
- `CHECK_INTERVAL_SECONDS`: Worker polling interval in seconds (default: 60)
- `LOG_LEVEL`: Logging level - DEBUG, INFO, WARNING, ERROR (default: INFO)

### 3. Start the Application

```bash
docker-compose up -d
```

Or with environment file:

```bash
docker-compose --env-file .env up -d
```

### 4. Monitor and Verify

#### Check Container Status
```bash
docker-compose ps
```

#### View Logs
```bash
docker-compose logs -f app
```

#### Health Check
```bash
curl http://localhost:8000/health
```

## Startup Process Explained

When the container starts, the following sequence occurs:

1. **Alembic Database Migrations** (from Dockerfile CMD)
   - `alembic upgrade head`
   - Applies all pending database migrations
   - Fails container startup if migrations fail (preserving data consistency)

2. **Supervisord Initialization**
   - `supervisord -c /app/supervisord.conf -n` (no-daemon mode required for Docker)
   - Reads [supervisord] and [program:*] configurations
   - Starts configured programs with autostart=true

3. **Worker Daemon** (managed by supervisord)
   - Executes: `python -m quant_stickynote.worker`
   - Imports worker module → calls main() → Worker.run()
   - Enters infinite loop checking should_execute()
   - Every CHECK_INTERVAL_SECONDS, checks if current UTC time >= TRIGGER_TIME
   - Once per day at TRIGGER_TIME, executes all enabled queries
   - Processes signals and persists to signal_archive table

4. **Health Check**
   - Supervisord runs continuously
   - Container exposes /health endpoint (via api.py)
   - Docker health check probes every 30 seconds

## Configuration Files

### supervisord.conf
Located in project root.

**Key Settings:**
- `nodaemon=true` - Required for Docker (prevents supervisord from forking)
- `logfile=/dev/null` - Supervisord master logs to null
- `[program:worker]` - Worker daemon configuration
  - `command=python -m quant_stickynote.worker` - Module execution with main()
  - `directory=/app` - Working directory
  - `autostart=true` - Start with supervisord
  - `autorestart=true` - Restart if process exits
  - `startretries=3` - Number of restart attempts
  - `stdout_logfile=/dev/stdout` - Log to stdout (Docker standard)
  - `stderr_logfile=/dev/stderr` - Log to stderr (Docker standard)

### Dockerfile
Multi-stage production image following backend coding standards:

**Key Stages:**
- Base: `python:3.12-slim`
- Install supervisor, curl (for healthcheck)
- Copy: pyproject.toml, README.md, src/, alembic/, alembic.ini, supervisord.conf
- User: Runs as `appuser` (non-root for security)
- Expose: Port 8000
- Healthcheck: Probes /health endpoint every 30s
- CMD: `alembic upgrade head && supervisord -c /app/supervisord.conf -n`

### docker-compose.yml
Local development and deployment orchestration:

```yaml
version: "3.8"
services:
  app:
    build: .  # Builds from Dockerfile
    environment:
      DATABASE_URL: "${DATABASE_URL}"
      TRIGGER_TIME: "${TRIGGER_TIME:-09:30}"
      CHECK_INTERVAL_SECONDS: "${CHECK_INTERVAL_SECONDS:-60}"
      LOG_LEVEL: "${LOG_LEVEL:-INFO}"
    expose:
      - "8000"
    ports:
      - "8000:8000"
```

## Query Configuration

Queries are defined in `queries/*.json` and execute once per day:

Example: `queries/long_term_momentum_short_term_pullback.json`

```json
{
  "id": "long_term_momentum_short_term_pullback",
  "enabled": true,
  "symbol_query": "SELECT ticker FROM ... WHERE ...",
  "price_query": "SELECT value FROM ... WHERE symbol = :symbol",
  "signal_extraction": {
    "symbol_column": "ticker",
    "buy_price_column": "value"
  }
}
```

**Requirements:**
- `enabled: true` - Only enabled queries execute
- `symbol_query` - Returns candidate symbols
- `price_query` - Parameterized with `:symbol`, returns price for each symbol
- `signal_extraction` - Maps result columns to signal fields

## Logs and Monitoring

### Log Output

All logs are written to stdout/stderr for Docker standard logging:

```bash
# View real-time logs
docker-compose logs -f app

# View last 100 lines
docker-compose logs --tail 100 app

# Save logs to file
docker-compose logs app > app.log
```

### Log Levels

Set `LOG_LEVEL` environment variable:
- `DEBUG`: Verbose, including query execution details
- `INFO`: Standard operational info (default)
- `WARNING`: Issues that don't prevent execution
- `ERROR`: Failures that impact signal processing

### Health Monitoring

Container includes Dockerfile healthcheck:

```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1
```

Healthy status means:
- Supervisord running
- Worker daemon started
- API available

## Troubleshooting

### Container Won't Start

1. Check logs for migration errors:
   ```bash
   docker-compose logs app | grep -i "alembic\|error"
   ```

2. Verify DATABASE_URL is set and correct:
   ```bash
   docker-compose config | grep DATABASE_URL
   ```

3. Test database connection:
   ```bash
   docker-compose exec app python -c \
     "from sqlalchemy import create_engine; \
      engine = create_engine('${DATABASE_URL}'); \
      engine.connect()"
   ```

### Worker Not Executing Queries

1. Check if queries are enabled:
   ```bash
   docker-compose exec app ls queries/
   cat queries/example.json | grep '"enabled"'
   ```

2. Verify trigger time (UTC):
   ```bash
   docker-compose logs app | grep -i "should_execute"
   ```

3. Check query results:
   ```bash
   docker-compose logs app | grep -i "signal\|query"
   ```

### High Memory or CPU Usage

1. Adjust CHECK_INTERVAL_SECONDS if polling too frequently:
   ```bash
   # In docker-compose.yml or .env
   CHECK_INTERVAL_SECONDS=300  # 5 minute intervals
   ```

2. Review query complexity - optimize symbol_query and price_query

### Migration Failures

1. Check alembic version:
   ```bash
   docker-compose exec app alembic current
   ```

2. View migration history:
   ```bash
   docker-compose exec app alembic history
   ```

3. Attempt manual migration:
   ```bash
   docker-compose exec app alembic upgrade head
   ```

## Scaling Considerations

### Multiple Worker Instances

Current design supports single worker per container. For parallel signal processing:

1. Create multiple service definitions in docker-compose.yml
2. Each runs independent worker with separate schedules
3. Signal deduplication via signal_archive table prevents duplicates

### Production Deployment

For Kubernetes or other orchestration:

1. Push image to registry:
   ```bash
   docker tag quant-sticky-note:latest myregistry/quant-sticky-note:latest
   docker push myregistry/quant-sticky-note:latest
   ```

2. Deploy with DATABASE_URL secret management (not in compose)

3. Configure persistent volume for alembic versions if needed

## Security Considerations

- **Non-root User**: Runs as `appuser` (UID > 1000)
- **Secret Management**: DATABASE_URL via environment (use secrets management in production)
- **.dockerignore**: Excludes unnecessary files (reduces image size and exposure)
- **Minimal Dependencies**: Only supervisor, curl, and Python runtime
- **Health Checks**: Allows orchestration to restart unhealthy containers

## Standards Compliance

This deployment follows the BACKEND_CODING_STANDARDS.md specifications:

- ✅ **Section 9** (Alembic): Migrations run before app starts
- ✅ **Section 10** (Entry Points): Worker has main() function and __name__ block
- ✅ **Section 11** (Supervisord): Proper config with stdout_logfile, autorestart, nodaemon
- ✅ **Section 12** (Dockerfile): Non-root user, HEALTHCHECK, EXPOSE, alembic in CMD
- ✅ **Section 13** (.dockerignore): Excludes build artifacts
- ✅ **Section 14** (docker-compose.yml): Environment-driven configuration

## Next Steps

1. **Set DATABASE_URL** to your data warehouse connection string
2. **Build image**: `docker build -t quant-sticky-note:latest .`
3. **Start services**: `docker-compose up -d`
4. **Monitor logs**: `docker-compose logs -f app`
5. **Verify health**: `curl http://localhost:8000/health`
