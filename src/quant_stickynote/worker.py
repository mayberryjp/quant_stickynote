"""Background worker daemon for periodic query execution.

The worker runs in a loop that:
1. Checks if current time has reached TRIGGER_TIME (UTC)
2. If triggered:
   - Loads all enabled query definitions
   - Executes each query against its external database
   - Processes results and extracts signals
   - Persists signals to sticky_notes table
   - Records execution details to query_executions audit table
3. Sleeps for CHECK_INTERVAL_SECONDS before next check
4. Logs execution summary at regular intervals (every N cycles)

Configuration:
- TRIGGER_TIME: Time (UTC) to execute queries (HH:MM format)
- CHECK_INTERVAL_SECONDS: How often to check (default: 60)
- WORKER_LOG_EVERY_N_CYCLES: Log summary every N cycles (default: 10)

Usage:
    from worker import Worker
    
    worker = Worker()
    worker.run()  # Runs forever until KeyboardInterrupt
"""
import time
from datetime import datetime, timezone
from typing import Optional

from config import settings
from logger import get_logger, log_query_execution
from query_engine import get_query_engine
from signal_processor import SignalProcessor

log = get_logger(__name__)


class Worker:
    """Background daemon for periodic query execution."""

    def __init__(self):
        """Initialize worker."""
        self.query_engine = get_query_engine()
        self.cycle_count = 0
        self.running = False
        self.last_run_date = None  # date of last successful execution

    def should_execute(self) -> bool:
        """Return True once per day when current UTC time has passed trigger time."""
        now = datetime.now(timezone.utc)
        today = now.date()
        if self.last_run_date == today:
            return False  # already ran today
        return now.time() >= settings.trigger_time_parsed

    def execute_queries(self) -> None:
        """Execute all enabled queries and process signals.
        
        Steps:
        1. Get all enabled queries from query definitions
        2. For each query:
           a. Execute SQL query against external database
           b. Parse results and extract signals
           c. Persist signals to sticky_notes with deduplication
           d. Record execution to audit table
        3. Log summary
        """
        start_time = datetime.now(timezone.utc)
        enabled_queries = self.query_engine.get_enabled_queries()

        if not enabled_queries:
            log.warning("No enabled queries found")
            return

        log.info("Query execution cycle started", query_count=len(enabled_queries))
        total_row_count = 0
        total_signals_extracted = 0
        total_signals_saved = 0
        errors = []

        for query in enabled_queries:
            try:
                # Time the execution
                query_start = datetime.now(timezone.utc)

                # Execute query
                signals, error = self.query_engine.execute_query(query)
                row_count = 0  # We don't have row count from engine currently

                if error:
                    log.error(
                        "Query execution failed",
                        query_id=query.id,
                        error=error,
                    )
                    SignalProcessor._record_execution(
                        query_id=query.id,
                        status="error",
                        row_count=0,
                        signals_extracted=len(signals),
                        duration_ms=0,
                        error_message=error,
                    )
                    errors.append((query.id, error))
                    continue

                # Process signals
                signals_saved, process_error = SignalProcessor.process_signals(
                    query_id=query.id,
                    signals=signals,
                    row_count=row_count,
                    execution_time_ms=int(
                        (datetime.now(timezone.utc) - query_start).total_seconds() * 1000
                    ),
                )

                total_signals_extracted += len(signals)
                total_signals_saved += signals_saved

                if process_error:
                    errors.append((query.id, process_error))

            except Exception as e:
                log.error(
                    "Unexpected error executing query",
                    query_id=query.id,
                    error_type=type(e).__name__,
                    error=str(e),
                )
                errors.append((query.id, str(e)))

        # Log summary
        execution_time_ms = int(
            (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        )
        log.info(
            "Query execution cycle completed",
            query_count=len(enabled_queries),
            signals_extracted=total_signals_extracted,
            signals_saved=total_signals_saved,
            errors=len(errors),
            duration_ms=execution_time_ms,
        )

        self.last_run_date = datetime.now(timezone.utc).date()

        if errors:
            log.warning(
                "Some queries failed",
                error_count=len(errors),
                errors=errors,
            )

    def run(self) -> None:
        """Run worker loop indefinitely.
        
        Loop:
        1. Check if trigger time reached (current time >= TRIGGER_TIME)
        2. If triggered, execute all enabled queries
        3. Sleep for CHECK_INTERVAL_SECONDS
        4. Log summary every WORKER_LOG_EVERY_N_CYCLES cycles
        
        Exits on KeyboardInterrupt (Ctrl+C)
        """
        self.running = True
        log.info(
            "Worker daemon started",
            trigger_time=settings.trigger_time,
            check_interval=settings.check_interval_seconds,
            log_every_n_cycles=settings.worker_log_every_n_cycles,
        )

        try:
            while self.running:
                self.cycle_count += 1

                # Check if it's time to execute
                if self.should_execute():
                    self.execute_queries()

                # Log cycle summary periodically
                if self.cycle_count % settings.worker_log_every_n_cycles == 0:
                    log.info(
                        "Worker cycle summary",
                        cycles=self.cycle_count,
                        uptime_minutes=self.cycle_count
                        * settings.check_interval_seconds
                        / 60,
                    )

                # Sleep until next check
                time.sleep(settings.check_interval_seconds)

        except KeyboardInterrupt:
            log.info("Worker shutdown requested via KeyboardInterrupt")
        except Exception as e:
            log.error(
                "Worker error",
                error_type=type(e).__name__,
                error=str(e),
            )
            raise
        finally:
            self.running = False
            log.info(
                "Worker daemon stopped",
                total_cycles=self.cycle_count,
            )

    def stop(self) -> None:
        """Stop worker daemon gracefully.
        
        Sets running flag to False, which will cause run() loop to exit
        after current sleep interval completes.
        """
        self.running = False
        log.info("Worker stop requested")


# Global worker instance
_worker_instance: Optional[Worker] = None


def get_worker() -> Worker:
    """Get or create worker singleton.
    
    Returns:
        Worker instance
    """
    global _worker_instance
    if _worker_instance is None:
        _worker_instance = Worker()
    return _worker_instance

def main() -> None:
    """Main entry point for worker daemon.
    
    Called by supervisord or direct invocation.
    """
    worker = get_worker()
    worker.run()


if __name__ == "__main__":
    main()
