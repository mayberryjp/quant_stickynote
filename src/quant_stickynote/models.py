"""SQLAlchemy ORM models for quant_stickynote service."""
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import declarative_base

# Create the declarative base class for all models
Base = declarative_base()


class PositionType(str, Enum):
    """Enum for position type (LONG or SHORT)."""
    LONG = "LONG"
    SHORT = "SHORT"


class SignalStatus(str, Enum):
    """Enum for signal/sticky note status."""
    ACTIVE = "active"
    REVIEWED = "reviewed"
    CANCELLED = "cancelled"
    EXECUTED = "executed"


class ExecutionStatus(str, Enum):
    """Enum for query execution status."""
    SUCCESS = "success"
    ERROR = "error"
    SKIPPED = "skipped"


class StickyNote(Base):
    """ORM model for sticky notes table.
    
    Represents a trading signal discovered by a query: stock symbol
    to watch, recommended entry price, when to go LONG or SHORT,
    status tracking, and metadata about the triggering query.
    
    Attributes:
        id: Unique identifier (primary key)
        symbol: Stock ticker symbol (e.g., 'AAPL')
        trigger_reason: Name/description of the rule that generated this signal
        buy_price: Recommended entry price (NUMERIC 10,4)
        position_type: Direction of trade - 'LONG' (buy/bull) or 'SHORT' (sell/bear)
        created_at: UTC timestamp when signal was generated
        signal_date: UTC calendar date (yyyy-mm-dd) the signal was generated
        source_query_id: Reference to the query definition that produced this signal
        status: Lifecycle state (active, reviewed, cancelled, executed)
        notes: Optional manual notes from trader
        updated_at: UTC timestamp of last modification
    """

    __tablename__ = "sticky_notes"
    __table_args__ = (
        # No DB-level unique constraint on (symbol, trigger_reason) — dedup is per-day in code
        CheckConstraint("position_type IN ('LONG', 'SHORT')", name="ck_position_type"),
        CheckConstraint(
            "status IN ('active', 'reviewed', 'cancelled', 'executed')",
            name="ck_status"
        ),
        Index("idx_sticky_notes_symbol", "symbol"),
        Index("idx_sticky_notes_created_at", "created_at"),
        Index("idx_sticky_notes_status", "status"),
        Index("idx_sticky_notes_position_type", "position_type"),
        Index("idx_sticky_notes_signal_date", "signal_date"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False, doc="Stock ticker symbol")
    trigger_reason = Column(String(255), nullable=False, doc="Query/rule name that generated signal")
    buy_price = Column(Numeric(precision=10, scale=4), nullable=False, doc="Recommended entry price")
    position_type = Column(
        String(10),
        nullable=False,
        default=PositionType.LONG.value,
        server_default=PositionType.LONG.value,
        doc="LONG (buy/bull) or SHORT (sell/bear)"
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        doc="UTC timestamp when signal was discovered"
    )
    signal_date = Column(
        Date,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).date(),
        server_default=func.current_date(),
        doc="UTC calendar date (yyyy-mm-dd) when signal was discovered"
    )
    source_query_id = Column(String(50), nullable=False, doc="Reference to triggering query definition")
    status = Column(
        String(20),
        nullable=False,
        default=SignalStatus.ACTIVE.value,
        server_default=SignalStatus.ACTIVE.value,
        doc="Lifecycle: active, reviewed, cancelled, executed"
    )
    notes = Column(Text, nullable=True, doc="Optional trader notes")
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        doc="UTC timestamp of last modification"
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<StickyNote(id={self.id}, symbol={self.symbol}, "
            f"position_type={self.position_type}, buy_price={self.buy_price}, "
            f"status={self.status})>"
        )

    def to_dict(self) -> dict:
        """Convert model to dictionary for API responses."""
        return {
            "id": self.id,
            "symbol": self.symbol,
            "trigger_reason": self.trigger_reason,
            "buy_price": float(self.buy_price) if self.buy_price else None,
            "position_type": self.position_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "signal_date": self.signal_date.isoformat() if self.signal_date else None,
            "source_query_id": self.source_query_id,
            "status": self.status,
            "notes": self.notes,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class QueryExecution(Base):
    """ORM model for query_executions audit log.
    
    Tracks execution history of each query: when it ran, how many rows
    were returned, signals extracted, success/failure status, and any
    error messages for debugging.
    
    Attributes:
        id: Unique identifier (primary key)
        query_id: Reference to the query definition
        executed_at: UTC timestamp when query execution started
        row_count: Number of rows returned by the query
        signals_extracted: Number of signals derived from results
        duration_ms: Query execution time in milliseconds
        status: Outcome (success, error, skipped)
        error_message: Error details if status is 'error'
        created_at: UTC timestamp when record was inserted
    """

    __tablename__ = "query_executions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('success', 'error', 'skipped')",
            name="ck_execution_status"
        ),
        Index("idx_query_executions_query_id", "query_id", "executed_at"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    query_id = Column(String(50), nullable=False, doc="Reference to query definition")
    executed_at = Column(
        DateTime(timezone=True),
        nullable=False,
        doc="UTC timestamp when execution started"
    )
    row_count = Column(Integer, nullable=True, doc="Rows returned from query")
    signals_extracted = Column(Integer, nullable=True, doc="Number of signals generated")
    duration_ms = Column(Integer, nullable=True, doc="Execution time in milliseconds")
    status = Column(
        String(20),
        nullable=False,
        doc="Execution outcome: success, error, or skipped"
    )
    error_message = Column(Text, nullable=True, doc="Error details if status=error")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        doc="UTC timestamp when record was inserted"
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<QueryExecution(id={self.id}, query_id={self.query_id}, "
            f"status={self.status}, signals_extracted={self.signals_extracted})>"
        )

    def to_dict(self) -> dict:
        """Convert model to dictionary for API responses."""
        return {
            "id": self.id,
            "query_id": self.query_id,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "row_count": self.row_count,
            "signals_extracted": self.signals_extracted,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
