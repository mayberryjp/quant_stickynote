# Production Deployment Checklist

Complete checklist for deploying Quant Sticky Note to production.

## Pre-Deployment Requirements

### Infrastructure
- [ ] External PostgreSQL database available with data warehouse schema
- [ ] Database credentials and connection string ready (in DATABASE_URL format)
- [ ] Docker runtime available (Docker Desktop or Docker Engine)
- [ ] Docker Compose installed (v1.29+ recommended)
- [ ] Network connectivity to external database from container runtime

### Configuration
- [ ] Database connection tested and verified working
- [ ] `DATABASE_URL` environment variable documented
- [ ] `TRIGGER_TIME` UTC time determined for query execution schedule
- [ ] `CHECK_INTERVAL_SECONDS` polling interval chosen (default 60 ok for most cases)
- [ ] `LOG_LEVEL` set appropriately (INFO recommended for production)

### Code
- [ ] All queries in `queries/*.json` validated and tested
- [ ] At least one query has `"enabled": true` for testing
- [ ] Alembic migrations in `alembic/versions/` reviewed and ready
- [ ] `requirements.txt` and `setup.py` dependencies complete
- [ ] No uncommitted changes in working directory

## Docker Build & Image

### Build Process
- [ ] Run `docker build -t quant-sticky-note:latest .`
- [ ] Build completes without errors
- [ ] Image layers include: Python 3.12, supervisor, curl, dependencies
- [ ] Image size reasonable (check with `docker images | grep quant-sticky-note`)

### Image Validation
- [ ] Image tagged correctly (`quant-sticky-note:latest`)
- [ ] Image stored in accessible registry (Docker Hub, ECR, etc. for production)
- [ ] Image documentation available (Dockerfile comments clear)
- [ ] Security scan completed (if using vulnerability scanning)

## Container Startup & Initialization

### Alembic Migration Phase
- [ ] DATABASE_URL environment variable set correctly
- [ ] Run test: `docker run -e DATABASE_URL="..." quant-sticky-note:latest alembic current`
- [ ] Current migration version returned without error
- [ ] Run test: `docker run -e DATABASE_URL="..." quant-sticky-note:latest alembic history`
- [ ] Migration history displays correctly

### Supervisord Phase
- [ ] Dockerfile CMD contains: `alembic upgrade head && supervisord -c /app/supervisord.conf -n`
- [ ] supervisord.conf present in container at `/app/supervisord.conf`
- [ ] supervisord.conf has `nodaemon=true` (required for Docker)
- [ ] supervisord.conf has `[program:worker]` section with correct command

### Worker Process Phase
- [ ] supervisord starts worker via: `python -m quant_stickynote.worker`
- [ ] worker.py has `main()` function defined
- [ ] worker.py has `if __name__ == "__main__": main()` block
- [ ] Worker enters run loop and begins polling

## Container Deployment

### Docker Compose Setup
- [ ] docker-compose.yml present and valid YAML
- [ ] Service name is `app`
- [ ] Build context set to `.` (current directory)
- [ ] Environment variables section includes DATABASE_URL
- [ ] Environment variables section includes TRIGGER_TIME, CHECK_INTERVAL_SECONDS, LOG_LEVEL
- [ ] Port 8000 exposed and mapped to host

### Environment Variables File
- [ ] `.env.example` present with all variable names
- [ ] `.env` created with actual values (never commit .env)
- [ ] DATABASE_URL in .env matches external database connection string
- [ ] All required variables populated (only DATABASE_URL is truly required)

### Startup Verification
- [ ] Run: `docker-compose up -d`
- [ ] Container starts successfully (check with `docker-compose ps`)
- [ ] No error logs (check with `docker-compose logs --tail 50`)
- [ ] Wait 5-10 seconds for alembic migrations to complete
- [ ] Verify healthcheck passes: `docker-compose ps` shows healthy status
- [ ] Manual healthcheck: `curl -v http://localhost:8000/health`

## Runtime Monitoring

### Initial Startup
- [ ] All logs in first 30 seconds show alembic completing migrations
- [ ] No "ERROR" or "CRITICAL" level logs during startup
- [ ] Supervisord initialization logs visible
- [ ] Worker process visible in logs (CRIT or INFO level startup)

### First Execution Cycle
- [ ] Wait for TRIGGER_TIME to pass (or modify env var to test)
- [ ] Logs show "should_execute() = True" at trigger time
- [ ] Query execution logs visible (one per enabled query)
- [ ] Signal processing logs show counts: "Processed X signals"
- [ ] Signal archive persistence logs visible

### Health Monitoring
- [ ] Healthcheck passes continuously
- [ ] No memory leaks (memory usage stable in `docker stats`)
- [ ] CPU usage reasonable during idle periods
- [ ] CPU usage increases during TRIGGER_TIME window

### Log Output
- [ ] Logs to stdout/stderr only (no file logging)
- [ ] Log level appropriate (INFO is verbose enough)
- [ ] No PII or sensitive data in logs
- [ ] Timestamps in UTC (easy to correlate across systems)

## Operational Procedures

### Daily Verification
- [ ] Check logs once per day around TRIGGER_TIME
- [ ] Verify signal counts match query results
- [ ] Verify no error logs during execution
- [ ] Confirm container still healthy: `docker-compose ps`

### Scaling Strategy
- [ ] Determine if single worker sufficient or multiple needed
- [ ] If multiple workers: stagger TRIGGER_TIME per instance
- [ ] Signal deduplication via signal_archive handles concurrent writes
- [ ] Load testing completed (queries don't timeout, DB doesn't overload)

### Backup & Recovery
- [ ] Database backup strategy defined (external DB responsibility)
- [ ] Alembic migration state recoverable (version info in alembic_version table)
- [ ] Can rebuild image and redeploy at any time
- [ ] Persistent query results in signal_archive (survives container recreate)

### Update Process
- [ ] Process for updating queries without rebuilding image defined
- [ ] Process for upgrading database schema (alembic) documented
- [ ] Rollback procedure in place (prior image versions retained)
- [ ] Testing environment matches production (DATABASE_URL points to same external DB)

## Post-Deployment Success Criteria

### Functional Requirements
- ✅ Container starts automatically after host restart
- ✅ Alembic migrations run and complete successfully
- ✅ Worker daemon initializes and enters polling loop
- ✅ Queries execute at scheduled TRIGGER_TIME every day
- ✅ Signals persist to signal_archive table
- ✅ Healthcheck passes continuously
- ✅ Logs are readable and troubleshootable

### Performance Requirements
- ✅ Query execution completes within acceptable time
- ✅ Memory usage stable (no leaks)
- ✅ Database queries don't timeout
- ✅ CPU usage minimal during idle periods
- ✅ Container restart time < 30 seconds

### Operational Requirements
- ✅ Logs accessible via `docker-compose logs`
- ✅ Errors are identifiable and actionable
- ✅ No manual intervention required during normal operation
- ✅ Supervisord autorestart recovers from transient failures

## Coding Standards Compliance

### Backend Coding Standards
- ✅ Section 9 (Alembic): Migrations run at container startup
- ✅ Section 10 (Entry Points): Worker has main() and if __name__ block
- ✅ Section 11 (Supervisord): Proper nodaemon, logfile paths, program config
- ✅ Section 12 (Dockerfile): Non-root user, HEALTHCHECK, EXPOSE, CMD
- ✅ Section 13 (.dockerignore): Excludes build artifacts
- ✅ Section 14 (docker-compose.yml): Environment-driven, build context

## Rollback Procedure

If deployment fails:

1. **Verify previous version available**
   ```bash
   docker images | grep quant-sticky-note
   ```

2. **Switch to previous image tag**
   ```bash
   # In docker-compose.yml, change image: quant-sticky-note:latest to prior version
   docker-compose pull
   docker-compose up -d
   ```

3. **Check logs for root cause**
   ```bash
   docker-compose logs --tail 100
   ```

4. **Address issue and rebuild**
   ```bash
   # Fix code/configuration
   docker build -t quant-sticky-note:v2 .
   # Update docker-compose.yml image tag
   docker-compose up -d
   ```

## Sign-Off

Deployment readiness sign-off:

- [ ] Reviewed and completed all pre-deployment requirements
- [ ] Docker image built and validated
- [ ] Container starts without errors
- [ ] Worker process executes queries on schedule
- [ ] Logs are accessible and clear
- [ ] Healthcheck passes
- [ ] Ready for production use

**Deployed by**: _______________
**Date**: _______________
**Environment**: _______________
**Database**: _______________
**Query Count**: ___ (enabled queries)

## Contact & Support

For issues or questions:
1. Check DEPLOYMENT.md troubleshooting section
2. Review logs: `docker-compose logs -f app`
3. Verify DATABASE_URL and network connectivity
4. Contact infrastructure team for Kubernetes/orchestration support
