# Quant Sticky Note - Backend Service

A Python backend service for continuous stock trading signal discovery via configurable SQL queries against external databases.

## Overview

**Purpose**: Execute scheduled SQL queries against external data sources, detect trading signals, and persist them to a local "sticky note" table for trader review.

**Key Features**:
- 🔄 Persistent daemon with scheduled execution
- 📊 Read from multiple external databases
- 🎯 Modular query engine (JSON-based query definitions)
- 📝 Sticky note storage (symbol, reason, buy price, timestamp)
- 🚀 REST API for querying and managing signals
- 📈 Comprehensive logging and monitoring
- 🐳 Docker + supervisord deployment ready
- ✅ Follow quant stack coding standards and patterns

## Quick Start

### Prerequisites
- Python 3.12+
- PostgreSQL 13+
- Docker (for containerized deployment)
- Git

### Local Development Setup

1. **Clone and enter directory**
   ```bash
   cd c:\Users\rimayber\quant_stickynote
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # or `venv\Scripts\activate` on Windows
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
  pip install -r requirements-dev.txt  # for tests and tooling
   ```

4. **Set up local PostgreSQL**
   ```bash
   # Option 1: Using docker-compose
  docker-compose up -d
   
   # Option 2: Manual PostgreSQL setup
   createdb quant_stickynote
   export DATABASE_URL="postgresql://user:pass@localhost:5432/quant_stickynote"
   ```

5. **Run migrations**
   ```bash
   alembic upgrade head
   ```

6. **Start service (all modes)**
   ```bash
   # API + Worker (default)
   python -m quant_stickynote.main
   
   # API only
   python -m quant_stickynote.main --api-only
   
   # Worker only
   python -m quant_stickynote.main --worker-only
   ```

7. **Verify health**
   ```bash
   curl http://localhost:8080/health
   curl http://localhost:8080/ready
   ```

## Project Structure

```
quant_stickynote/
├── src/quant_stickynote/          # Main package
│   ├── __init__.py
│   ├── main.py                    # Entry point, CLI args
│   ├── config.py                  # Pydantic settings
│   ├── database.py                # SQLAlchemy setup
│   ├── models.py                  # ORM models (StickyNote, QueryExecution)
│   ├── api.py                     # Bottle app (endpoints)
│   ├── worker.py                  # Daemon loop
│   ├── query_engine.py            # Query loading & execution
│   ├── signal_processor.py        # Dedup & persistence
│   ├── logger.py                  # Structured logging
│   └── exceptions.py              # Custom exceptions
├── alembic/                       # Database migrations
│   ├── versions/
│   ├── env.py
│   └── alembic.ini
├── queries/                       # Query definitions (JSON)
│   ├── README.md                  # How to write queries
│   ├── example_momentum.json
│   └── example_rsi_oversold.json
├── supervisord/                   # Process management
│   ├── supervisord.conf
│   └── conf.d/quant_stickynote.conf
├── tests/
│   ├── unit/
│   └── integration/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
├── setup.py
├── pytest.ini
├── SPEC.md                        # Detailed specification
├── README.md                      # This file
└── CONTRIBUTING.md                # Developer guide
```

## Key Concepts

### Sticky Note
A record of a potential stock trading signal discovered by a query.

**Fields**:
- `symbol`: Stock ticker (e.g., "AAPL")
- `trigger_reason`: Why this signal was generated (e.g., "RSI Oversold")
- `buy_price`: Recommended entry price
- `position_type`: Direction of trade - `LONG` (buy/bull) or `SHORT` (sell/bear)
- `created_at`: When the signal was created
- `source_query_id`: Which query produced this signal
- `status`: Current state (active, reviewed, cancelled, executed)

### Query Definition
JSON file in `queries/` directory defining how to discover signals.

**Example** (`queries/momentum_breakout.json`):
```json
{
  "id": "momentum_001",
  "name": "Momentum Breakout",
  "description": "Stocks with increasing momentum scores",
  "enabled": true,
  "external_database": {
    "url": "postgresql://user:pass@data-warehouse:5432/market_data"
  },
  "source_query": "SELECT symbol, price FROM signals WHERE score > 0.75",
  "signal_extraction": {
    "symbol_column": "symbol",
    "buy_price_column": "price"
  }
}
```

See [queries/README.md](queries/README.md) for full schema and examples.

### Execution Flow

```
┌─ Service Starts
│  ├─ Load config from environment
│  ├─ Connect to local PostgreSQL
│  ├─ Initialize Bottle API server
│  └─ Load query definitions from queries/ folder
│
└─ Main Loop (if worker enabled)
   └─ Check time every 60 seconds (configurable)
      └─ If trigger time reached:
         └─ For each enabled query:
            ├─ Connect to external database
            ├─ Execute source_query
            ├─ Extract signals (symbol + price)
            ├─ Check for duplicates
            ├─ Insert new signals to sticky_notes table
            ├─ Log results to query_executions table
            └─ Continue to next query
      └─ Sleep 60 seconds
      └─ Repeat
```

## Configuration

### Environment Variables

Set these before running the service. See `.env.example` for template.

```bash
# Service Info
SERVICE_NAME=quant_stickynote
LOG_LEVEL=DEBUG|INFO|WARNING|ERROR

# Database (Local)
DATABASE_URL=postgresql://user:password@localhost:5432/quant_stickynote

# Scheduling
TRIGGER_TIME=09:30              # HH:MM UTC
CHECK_INTERVAL_SECONDS=60       # How often to check time

# API Server
API_HOST=0.0.0.0
API_PORT=8080
API_WORKERS=20

# Worker Process
WORKER_ENABLED=true
WORKER_LOG_EVERY_N_CYCLES=10
```

### File-Based Configuration
Configuration can also be loaded from a YAML/TOML file (see `config.py` for implementation details).

## Development Workflow

### Running Tests
```bash
# All tests
pytest

# With coverage
pytest --cov=src/quant_stickynote

# Specific test file
pytest tests/unit/test_query_engine.py -v

# Watch mode (optional with pytest-watch)
ptw
```

### Code Style
```bash
# Format with Black
black src/ tests/

# Lint with flake8
flake8 src/ tests/

# Sort imports with isort
isort src/ tests/

# Run all together
make lint
```

### Database Migrations
```bash
# Create a new migration (auto-detect schema changes)
alembic revision --autogenerate -m "Add new column"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Check current version
alembic current
```

### Adding a New Query
1. Create JSON file in `queries/` directory
2. Define `id`, `name`, `source_query`, `signal_extraction`
3. Set `enabled: true`
4. Restart service or trigger reload (see API docs)

Example:
```bash
cat > queries/my_new_signal.json << 'EOF'
{
  "id": "my_signal_001",
  "name": "My New Signal",
  "description": "Does something interesting",
  "enabled": true,
  "external_database": {
    "url": "postgresql://...your-db..."
  },
  "source_query": "SELECT symbol, price FROM your_table WHERE condition",
  "signal_extraction": {
    "symbol_column": "symbol",
    "buy_price_column": "price"
  }
}
EOF
```

## API Endpoints

### Health & Status
- `GET /health` - Service health
- `GET /ready` - Readiness (includes DB status)

### Sticky Notes
- `GET /sticky-notes` - List active signals
  - Query params: `limit`, `offset`, `symbol`, `status`
- `GET /sticky-notes/{id}` - Get single signal
- `POST /sticky-notes/{id}/status` - Update status
  - Body: `{"status": "reviewed|cancelled|executed"}`

### Queries
- `GET /queries` - List all loaded query definitions
- `GET /queries/{id}/executions` - Query execution history
- `GET /queries/{id}/last-execution` - Last run status

Example:
```bash
# Get recent active signals
curl "http://localhost:8080/sticky-notes?limit=10&status=active"

# Get signals for a symbol
curl "http://localhost:8080/sticky-notes?symbol=AAPL"

# Update signal status
curl -X POST http://localhost:8080/sticky-notes/123/status \
  -H "Content-Type: application/json" \
  -d '{"status": "executed"}'

# List queries
curl http://localhost:8080/queries

# Get execution history
curl "http://localhost:8080/queries/momentum_001/executions?limit=20"
```

## Deployment

### Docker

**Build**:
```bash
docker build -t quant_stickynote:latest .
```

**Run**:
```bash
docker run -d \
  -e DATABASE_URL="postgresql://..." \
  -e TRIGGER_TIME="09:30" \
  -p 8080:8080 \
  --name stickynote \
  quant_stickynote:latest
```

**With docker-compose**:
```bash
docker-compose up -d
```

### Supervisord

Install supervisord:
```bash
pip install supervisor
```

Copy config:
```bash
sudo cp supervisord/supervisord.conf /etc/supervisor/
sudo cp supervisord/conf.d/quant_stickynote.conf /etc/supervisor/conf.d/
```

Start:
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start quant_stickynote
```

Check status:
```bash
sudo supervisorctl status
sudo tail -f /var/log/quant_stickynote.log
```

## Monitoring & Troubleshooting

### Logs
All logs are structured JSON for easy parsing.

Example:
```json
{
  "timestamp": "2026-08-10T09:30:15.123Z",
  "level": "INFO",
  "service": "quant_stickynote",
  "message": "Query executed successfully",
  "query_id": "momentum_001",
  "signals_extracted": 5,
  "duration_ms": 250
}
```

### Common Issues

**Q: No signals inserted**
- Check query_executions table for errors
- Verify external_database URL is correct
- Check source_query syntax in external database
- Review logs: `grep "error" /var/log/quant_stickynote.log`

**Q: Duplicate signals**
- Check UNIQUE constraint on (symbol, trigger_reason, created_at)
- Verify dedup_key_ttl_hours in query definition
- Check query_executions for same query run twice

**Q: Service crashes after startup**
- Check DATABASE_URL is valid
- Run `alembic upgrade head` to ensure migrations applied
- Check Python version is 3.12+
- Review logs for specific errors

**Q: API not responding**
- Check if API_PORT is not in use: `netstat -an | grep 8080`
- Verify API_HOST binding: check config
- Try running with `--api-only` flag to test

### Debugging

Enable debug logging:
```bash
export LOG_LEVEL=DEBUG
python -m quant_stickynote.main
```

Query execution history:
```sql
SELECT * FROM query_executions 
ORDER BY executed_at DESC 
LIMIT 20;
```

Recent signals:
```sql
SELECT symbol, trigger_reason, created_at, status 
FROM sticky_notes 
ORDER BY created_at DESC 
LIMIT 50;
```

## Performance Considerations

- **Query Timeout**: 300 seconds (configurable, see config)
- **Check Interval**: 60 seconds (check if trigger time every minute)
- **Connection Pool**: 5 connections per external database (configurable)
- **Memory**: ~200-500MB steady state
- **Startup**: ~5 seconds

For high-volume queries, consider:
- Increasing external DB pool size
- Adding Redis caching layer
- Running multiple workers with load balancer

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines, code style, testing strategy, and pull request process.

## Architecture & Design Details

See [SPEC.md](SPEC.md) for:
- Detailed architecture diagrams
- Complete database schema
- Progressive implementation slices
- Coding standards and best practices
- Query definition JSON schema
- Performance targets

See [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) for:
- How to apply database migrations with Alembic
- Schema version management
- Creating and running new migrations
- Troubleshooting database setup issues

## Reference Repositories

This project follows patterns from:
- [quant_momentum](https://github.com/mayberryjp/quant_momentum) - Bottle/API patterns
- [quant_signals](https://github.com/mayberryjp/quant_signals) - Query execution and dedup
- [quant_daily_bars](https://github.com/mayberryjp/quant_daily_bars) - Data ingestion patterns

Backend Coding Standards:
- https://github.com/mayberryjp/coding_standards/blob/main/BACKEND_CODING_STANDARDS.md

## License

[Your License Here]

## Support

For issues, questions, or suggestions:
1. Check [CONTRIBUTING.md](CONTRIBUTING.md) first
2. Create an issue with detailed reproduction steps
3. Include logs, config (sanitized), and environment info
4. Contact project lead if urgent

---

**Last Updated**: 2026-08-10  
**Maintained By**: [Your Team]
- [ ] For bars: Set POLYGON_API_KEY
- [ ] Start services on desired ports
- [ ] Test API endpoints with curl/Postman
- [ ] Monitor job runs and error logs

## 🔗 API Endpoints Quick Reference

### quant_signals
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/signals` | Submit new signal |
| GET | `/signals/recent` | Get recent signals |
| GET | `/watchlist` | Query watchlist |
| GET | `/watchlist/<id>` | Get watchlist entry |
| PATCH | `/watchlist/<id>` | Update watchlist entry |

### quant_daily_bars
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/ingest` | Trigger async ingestion |
| GET | `/ingest/jobs` | List ingest jobs |
| GET | `/ingest/jobs/<id>` | Get job details |
| GET | `/bars` | Query bars |
| GET | `/bars/<ticker>/summary` | Bar summary |
| GET | `/bars/date-range` | Min/max dates |

## 💾 Data Storage

All notes are stored in your browser's **localStorage** under the key `stickyNotes`. 

### Export Notes
```javascript
// In browser console:
const notes = JSON.parse(localStorage.getItem('stickyNotes'));
console.log(JSON.stringify(notes, null, 2));
```

### Import Notes
```javascript
// In browser console:
const newNotes = [{id: 1, title: "...", ...}];
localStorage.setItem('stickyNotes', JSON.stringify(newNotes));
location.reload();
```

## 🎓 Learning Resources

### Inside the App
- Edit pre-loaded notes to add your own insights
- Create new notes for concepts you want to remember
- Use categories to organize by service
- Search to find related concepts

### External Resources
- Visit the GitHub repos directly:
  - github.com/mayberryjp/quant_momentum
  - github.com/mayberryjp/quant_signals
  - github.com/mayberryjp/quant_daily_bars

## 🐛 Troubleshooting

### Notes Not Saving?
- Clear browser cache/localStorage
- Try a different browser
- Check browser console for errors (F12)

### Styling Issues?
- Hard refresh browser (Ctrl+Shift+R or Cmd+Shift+R)
- Disable browser extensions
- Try a different browser

### Can't Open index.html?
- Use Python server method (see Quick Start)
- Or use Live Server extension in VS Code

## 📝 Example Workflows

### Learning the Stack
1. Open index.html
2. Read through pre-loaded notes
3. Click each note to understand the architecture
4. Create a new note for each concept you want to master
5. Use search to explore relationships

### During Development
1. Keep the sticky note app open in a browser tab
2. Quickly reference API endpoints
3. Check configuration requirements
4. Remember key concepts without switching apps

### Documentation Review
1. Cross-reference with ARCHITECTURE_SUMMARY.md
2. Add clarifications as notes
3. Track changes and updates
4. Share insights with team

## 📄 License

These materials are for educational and reference purposes.

## 📧 Support

For issues with:
- **The sticky note app**: Check browser console (F12) for errors
- **Architecture questions**: Refer to ARCHITECTURE_SUMMARY.md
- **Service issues**: Check respective GitHub repositories

---

**Last Updated**: June 2026  
**Version**: 1.0  
**Repository**: quant_stickynote
