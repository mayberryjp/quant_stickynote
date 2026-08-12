"""Main entry point for quant_stickynote service.

Handles:
- Command-line argument parsing
- Configuration loading and validation
- Database initialization
- Service startup (API + Worker)

Usage:
    python -m quant_stickynote.main
    
    Options:
    --api-only       Run API server only (no background worker)
    --worker-only    Run worker daemon only (no API server)
    --debug          Enable debug mode (verbose logging)
    --help           Show help message

Environment:
    DATABASE_URL=postgresql://...
    TRIGGER_TIME=09:30
    API_HOST=0.0.0.0
    API_PORT=8080
    LOG_LEVEL=INFO
    (See .env.example for all options)

Examples:
    # Run both API and worker (default)
    python -m quant_stickynote.main
    
    # API server only (for scaling)
    python -m quant_stickynote.main --api-only
    
    # Worker only (separate process)
    python -m quant_stickynote.main --worker-only
    
    # Debug mode with verbose logging
    python -m quant_stickynote.main --debug
"""
import argparse
import sys
import threading
from typing import Optional

from waitress import serve

from api import get_app
from config import settings
from database import init_db
from exceptions import QuoteStickyNoteError
from logger import get_logger, log_startup, log_shutdown
from worker import get_worker

log = get_logger(__name__)


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments.
    
    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        prog="quant_stickynote",
        description="Quant Sticky Note trading signal discovery service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run API and worker together (default)
  python -m quant_stickynote.main
  
  # API server only
  python -m quant_stickynote.main --api-only
  
  # Worker daemon only
  python -m quant_stickynote.main --worker-only
  
  # Debug mode
  python -m quant_stickynote.main --debug

Environment Variables:
  DATABASE_URL           PostgreSQL connection string (required)
  API_HOST              API bind address (default: 0.0.0.0)
  API_PORT              API port (default: 8080)
  TRIGGER_TIME          Query execution time UTC HH:MM (default: 09:30)
  CHECK_INTERVAL_SECONDS Daemon check interval (default: 60)
  LOG_LEVEL             Logging level (default: INFO)
        """,
    )

    parser.add_argument(
        "--api-only",
        action="store_true",
        help="Run API server only (no background worker)",
    )

    parser.add_argument(
        "--worker-only",
        action="store_true",
        help="Run worker daemon only (no API server)",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode (verbose logging, SQL echoing)",
    )

    return parser.parse_args()


def validate_configuration(api_mode: bool = True, worker_mode: bool = True) -> None:
    """Validate configuration for selected modes.
    
    Args:
        api_mode: Whether API will be running
        worker_mode: Whether worker will be running
        
    Raises:
        ValueError: If configuration is invalid for selected modes
    """
    try:
        if api_mode:
            settings.validate_for_api()
        if worker_mode:
            settings.validate_for_worker()
    except ValueError as e:
        log.error("Configuration validation failed", error=str(e))
        raise


def initialize_database() -> bool:
    """Initialize database schema and verify migrations applied.
    
    Returns:
        True if database initialized successfully, False otherwise
    """
    try:
        result = init_db()
        log.info("Database initialized", message=result)
        return True
    except RuntimeError as e:
        log.error("Database initialization failed", error=str(e))
        return False


def run_api_server() -> None:
    """Start REST API server using Waitress.
    
    Runs on configured host:port with configured worker threads.
    Blocks until interrupted.
    """
    try:
        app = get_app()

        log.info(
            "Starting API server",
            host=settings.api_host,
            port=settings.api_port,
            workers=settings.api_workers,
        )

        # Waitress provides the WSGI server used by this service.
        serve(
            app,
            host=settings.api_host,
            port=settings.api_port,
            threads=settings.api_workers,
            _quiet=True,  # Suppress Waitress banner
        )

    except Exception as e:
        log.error(
            "API server error",
            error_type=type(e).__name__,
            error=str(e),
        )
        raise


def run_worker_daemon() -> None:
    """Start background worker daemon.
    
    Runs indefinitely, checking for trigger time and executing queries.
    Blocks until interrupted.
    """
    try:
        worker = get_worker()
        worker.run()

    except Exception as e:
        log.error(
            "Worker daemon error",
            error_type=type(e).__name__,
            error=str(e),
        )
        raise


def main() -> int:
    """Main service entry point.
    
    Returns:
        Exit code (0 = success, 1 = error)
    """
    # Parse arguments
    args = parse_arguments()

    # Apply debug mode if requested
    if args.debug:
        settings.debug = True
        settings.log_level = "DEBUG"

    # Determine which modes to run
    api_mode = not args.worker_only
    worker_mode = not args.api_only

    # Validate configuration for selected modes
    try:
        validate_configuration(api_mode=api_mode, worker_mode=worker_mode)
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    # Initialize database
    if not initialize_database():
        print("Failed to initialize database", file=sys.stderr)
        return 1

    # Log startup
    log_startup(version="1.0.0")

    try:
        if api_mode and worker_mode:
            # Run both API and worker in separate threads
            log.info("Running in combined mode (API + Worker)")

            api_thread = threading.Thread(
                target=run_api_server,
                name="API-Server",
                daemon=False,
            )
            worker_thread = threading.Thread(
                target=run_worker_daemon,
                name="Worker-Daemon",
                daemon=False,
            )

            # Start both threads
            api_thread.start()
            worker_thread.start()

            # Wait for both to complete
            api_thread.join()
            worker_thread.join()

        elif api_mode:
            # API only
            log.info("Running in API-only mode")
            run_api_server()

        elif worker_mode:
            # Worker only
            log.info("Running in worker-only mode")
            run_worker_daemon()

        else:
            # Should not reach here
            log.error("No mode selected (use --help)")
            return 1

        return 0

    except KeyboardInterrupt:
        log.info("Shutdown requested")
        return 0
    except Exception as e:
        log.error(
            "Fatal error",
            error_type=type(e).__name__,
            error=str(e),
        )
        return 1
    finally:
        log_shutdown(reason="Service terminated")


if __name__ == "__main__":
    sys.exit(main())
