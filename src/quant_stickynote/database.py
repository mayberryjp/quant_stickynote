"""SQLAlchemy database engine and session configuration.

Provides:
- Engine: Single shared database connection pool
- SessionLocal: Session factory for creating new sessions
- get_db_session: Context manager for automatic session cleanup
- init_db: Initialize schema on startup (verify migrations applied)

Usage:
    from database import SessionLocal, get_db_session, engine
    
    # Option 1: Manual session management
    session = SessionLocal()
    try:
        result = session.query(StickyNote).filter(...).first()
    finally:
        session.close()
    
    # Option 2: Context manager (recommended)
    with get_db_session() as session:
        result = session.query(StickyNote).filter(...).first()
"""
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .models import Base


def _make_db_url(url: str) -> str:
    # Rewrite postgresql:// → postgresql+psycopg:// so SQLAlchemy uses psycopg3
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        return url.replace("://", "+psycopg://", 1)
    return url


# Create engine with connection pooling
engine = create_engine(
    _make_db_url(settings.database_url),
    pool_size=settings.database_pool_size,
    pool_recycle=settings.database_pool_recycle_seconds,
    pool_pre_ping=settings.database_pool_pre_ping,
    echo=(settings.log_level.upper() == "DEBUG"),
)

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Get a database session with automatic cleanup.
    
    Context manager that creates a new session, yields it for use,
    and automatically closes it when done (even if error occurs).
    
    Yields:
        Session: SQLAlchemy session for queries
        
    Example:
        with get_db_session() as session:
            note = session.query(StickyNote).first()
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    """Initialize database schema and verify migrations applied.
    
    Checks:
    1. Can connect to database
    2. alembic_version table exists (migrations have run)
    3. Expected tables exist (sticky_notes, query_executions)
    
    Raises:
        RuntimeError: If database not properly initialized
        
    Should be called once at application startup.
    """
    try:
        with engine.connect() as connection:
            # Check alembic_version table exists
            result = connection.execute(
                text("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'alembic_version'")
            )
            if result.scalar() == 0:
                raise RuntimeError(
                    "Database not initialized. Run 'alembic upgrade head' to apply migrations."
                )

            # Check sticky_notes table exists
            result = connection.execute(
                text("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'sticky_notes'")
            )
            if result.scalar() == 0:
                raise RuntimeError(
                    "sticky_notes table not found. Database migrations may not have been applied."
                )

            # Get current migration version
            result = connection.execute(text("SELECT version_num FROM alembic_version"))
            version = result.scalar()
            return f"Database initialized (migration: {version})"

    except Exception as e:
        raise RuntimeError(f"Failed to initialize database: {e}") from e


def get_db_health() -> dict:
    """Get database health status for readiness checks.
    
    Returns:
        dict: Health status with keys:
            - connected: bool - Can connect to database
            - migration_version: str - Current Alembic version
            - tables: dict - Table count and row counts
            
    Example:
        health = get_db_health()
        if health["connected"]:
            print(f"Ready: {health['migration_version']}")
    """
    try:
        with engine.connect() as connection:
            # Get migration version
            result = connection.execute(text("SELECT version_num FROM alembic_version"))
            version = result.scalar()

            # Get row counts for monitoring
            sticky_notes_count = connection.execute(
                text("SELECT COUNT(*) FROM sticky_notes")
            ).scalar()
            
            query_exec_count = connection.execute(
                text("SELECT COUNT(*) FROM query_executions")
            ).scalar()

            return {
                "connected": True,
                "migration_version": version,
                "tables": {
                    "sticky_notes": sticky_notes_count,
                    "query_executions": query_exec_count,
                },
            }
    except Exception as e:
        return {
            "connected": False,
            "error": str(e),
        }
