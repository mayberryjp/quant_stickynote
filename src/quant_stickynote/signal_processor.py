"""Signal processing: deduplication, validation, and persistence to database.

Handles:
- Deduplication by (symbol, trigger_reason, date)
- Signal validation (required fields, reasonable values)
- Persistence to sticky_notes table
- Query execution audit logging to query_executions table
- Status management (active, reviewed, cancelled, executed)
- Error handling and recovery

Deduplication Logic:
Signals are unique within a 24-hour window by (symbol, trigger_reason, date).
If same signal detected multiple times in same day, only first is persisted.
This prevents duplicate alerts and trading on same signal multiple times.
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy import and_, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .database import get_db_session
from .exceptions import (
    DuplicateSignalError,
    DatabaseError,
    SignalExtractionError,
    ValidationError,
)
from .logger import get_logger
from .models import QueryExecution, StickyNote

log = get_logger(__name__)


class SignalProcessor:
    """Process and persist trading signals to database."""

    @staticmethod
    def process_signals(
        query_id: str,
        signals: List[dict],
        row_count: int = 0,
        execution_time_ms: int = 0,
    ) -> Tuple[int, Optional[str]]:
        """Process a batch of signals from query execution.
        
        Args:
            query_id: Source query identifier
            signals: List of signal dictionaries with keys:
                - symbol: Stock ticker
                - buy_price: Entry price
                - position_type: LONG or SHORT
                - trigger_reason: Signal reason
                - source_query_id: Query ID
            row_count: Number of rows queried
            execution_time_ms: Query execution time
            
        Returns:
            Tuple of (signals_saved, error_message):
            - signals_saved: Number of new signals persisted
            - error_message: Error string if failed, None if successful
        """
        if not signals:
            # No signals is not an error, just log and record empty execution
            SignalProcessor._record_execution(
                query_id=query_id,
                status="success",
                row_count=row_count,
                signals_extracted=0,
                duration_ms=execution_time_ms,
            )
            return 0, None

        signals_saved = 0
        signals_failed = 0

        with get_db_session() as session:
            try:
                for signal in signals:
                    try:
                        # Validate signal
                        SignalProcessor._validate_signal(signal)

                        # Check for duplicate
                        if SignalProcessor._signal_exists(session, signal):
                            log.info(
                                "Signal deduplicated",
                                symbol=signal["symbol"],
                                trigger_reason=signal["trigger_reason"],
                                source_query_id=signal["source_query_id"],
                            )
                            signals_failed += 1
                            continue

                        # Create StickyNote
                        note = StickyNote(
                            symbol=signal["symbol"],
                            trigger_reason=signal["trigger_reason"],
                            buy_price=signal["buy_price"],
                            position_type=signal.get("position_type", "LONG"),
                            source_query_id=signal["source_query_id"],
                            status="active",
                        )

                        session.add(note)
                        session.flush()  # Get ID before commit

                        log.info(
                            "Signal created",
                            signal_id=note.id,
                            symbol=note.symbol,
                            position_type=note.position_type,
                            buy_price=float(note.buy_price),
                            source_query_id=note.source_query_id,
                        )

                        signals_saved += 1

                    except (ValidationError, SignalExtractionError) as e:
                        log.warning(
                            "Signal validation failed",
                            source_query_id=query_id,
                            signal=signal,
                            error=str(e),
                        )
                        signals_failed += 1

                # Commit all signals at once
                session.commit()

                # Record execution
                SignalProcessor._record_execution(
                    query_id=query_id,
                    status="success",
                    row_count=row_count,
                    signals_extracted=len(signals),
                    signals_persisted=signals_saved,
                    duration_ms=execution_time_ms,
                )

                return signals_saved, None

            except IntegrityError as e:
                session.rollback()
                error_msg = f"Integrity constraint violation: {str(e)}"
                log.error(
                    "Integrity error",
                    query_id=query_id,
                    error=str(e),
                )
                SignalProcessor._record_execution(
                    query_id=query_id,
                    status="error",
                    row_count=row_count,
                    signals_extracted=len(signals),
                    duration_ms=execution_time_ms,
                    error_message=error_msg,
                )
                return signals_saved, error_msg

            except SQLAlchemyError as e:
                session.rollback()
                error_msg = f"Database error: {str(e)}"
                log.error(
                    "Database error processing signals",
                    query_id=query_id,
                    error=str(e),
                )
                SignalProcessor._record_execution(
                    query_id=query_id,
                    status="error",
                    row_count=row_count,
                    signals_extracted=len(signals),
                    duration_ms=execution_time_ms,
                    error_message=error_msg,
                )
                return signals_saved, error_msg

            except Exception as e:
                session.rollback()
                error_msg = f"Unexpected error: {str(e)}"
                log.error(
                    "Unexpected error processing signals",
                    query_id=query_id,
                    error_type=type(e).__name__,
                    error=str(e),
                )
                SignalProcessor._record_execution(
                    query_id=query_id,
                    status="error",
                    row_count=row_count,
                    signals_extracted=len(signals),
                    duration_ms=execution_time_ms,
                    error_message=error_msg,
                )
                return signals_saved, error_msg

    @staticmethod
    def _validate_signal(signal: dict) -> None:
        """Validate signal has all required fields and valid values.
        
        Args:
            signal: Signal dictionary to validate
            
        Raises:
            ValidationError: If signal is invalid
        """
        required_fields = ["symbol", "buy_price", "trigger_reason", "source_query_id"]

        for field in required_fields:
            if field not in signal:
                raise ValidationError(f"Signal missing required field: {field}")

        # Validate symbol format (1-10 character alphanumeric)
        symbol = str(signal["symbol"]).upper()
        if not (1 <= len(symbol) <= 10 and symbol.isalnum()):
            raise ValidationError(f"Invalid symbol: {signal['symbol']}")

        # Validate price is positive number
        try:
            price = float(signal["buy_price"])
            if price <= 0:
                raise ValidationError(f"Price must be positive: {price}")
        except (TypeError, ValueError) as e:
            raise ValidationError(f"Invalid price: {signal['buy_price']}") from e

        # Validate trigger_reason is not empty
        if not str(signal["trigger_reason"]).strip():
            raise ValidationError("trigger_reason cannot be empty")

        # Validate position_type if present
        position_type = signal.get("position_type", "LONG").upper()
        if position_type not in ("LONG", "SHORT"):
            raise ValidationError(f"Invalid position_type: {position_type}")

    @staticmethod
    def _signal_exists(session, signal: dict) -> bool:
        """Check if signal already exists (deduplication).
        
        Signals are unique within 24 hours by (symbol, trigger_reason, date).
        
        Args:
            session: SQLAlchemy session
            signal: Signal to check
            
        Returns:
            True if signal already exists, False otherwise
        """
        try:
            # Get today's date at start of day (UTC)
            today = datetime.now(timezone.utc).date()
            day_start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
            day_end = day_start + timedelta(days=1)

            # Query for existing signal
            existing = session.query(StickyNote).filter(
                and_(
                    StickyNote.symbol == signal["symbol"],
                    StickyNote.trigger_reason == signal["trigger_reason"],
                    StickyNote.created_at >= day_start,
                    StickyNote.created_at < day_end,
                )
            ).first()

            return existing is not None

        except Exception as e:
            log.error(
                "Error checking for duplicate signal",
                symbol=signal.get("symbol"),
                trigger_reason=signal.get("trigger_reason"),
                error=str(e),
            )
            # Fail safe: if we can't check, assume it exists to prevent duplicates
            return True

    @staticmethod
    def _record_execution(
        query_id: str,
        status: str,
        row_count: int = 0,
        signals_extracted: int = 0,
        signals_persisted: int = 0,
        duration_ms: int = 0,
        error_message: Optional[str] = None,
    ) -> None:
        """Record query execution in audit log.
        
        Args:
            query_id: Query identifier
            status: Execution status (success, error, skipped)
            row_count: Number of rows returned
            signals_extracted: Number of signals found
            signals_persisted: Number of signals saved
            duration_ms: Execution duration
            error_message: Error details if status=error
        """
        try:
            with get_db_session() as session:
                execution = QueryExecution(
                    query_id=query_id,
                    executed_at=datetime.now(timezone.utc),
                    row_count=row_count,
                    signals_extracted=signals_extracted,
                    duration_ms=duration_ms,
                    status=status,
                    error_message=error_message,
                )

                session.add(execution)
                session.commit()

                log.info(
                    "Execution recorded",
                    query_id=query_id,
                    status=status,
                    row_count=row_count,
                    signals_extracted=signals_extracted,
                    signals_persisted=signals_persisted,
                    duration_ms=duration_ms,
                )

        except Exception as e:
            log.error(
                "Failed to record execution",
                query_id=query_id,
                error=str(e),
            )


class SignalAnalyzer:
    """Analyze signals and provide statistics."""

    @staticmethod
    def get_today_summary() -> dict:
        """Get summary of signals created today.
        
        Returns:
            dict with keys:
            - total_signals: Total signals created today
            - by_position_type: {"LONG": count, "SHORT": count}
            - by_symbol: {"SYMBOL": count, ...}
            - total_value: Sum of buy_price for all signals
        """
        try:
            with get_db_session() as session:
                today = datetime.now(timezone.utc).date()
                day_start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
                day_end = day_start + timedelta(days=1)

                # Total signals
                total = session.query(func.count(StickyNote.id)).filter(
                    and_(
                        StickyNote.created_at >= day_start,
                        StickyNote.created_at < day_end,
                        StickyNote.status == "active",
                    )
                ).scalar() or 0

                # By position type
                position_counts = session.query(
                    StickyNote.position_type,
                    func.count(StickyNote.id),
                ).filter(
                    and_(
                        StickyNote.created_at >= day_start,
                        StickyNote.created_at < day_end,
                        StickyNote.status == "active",
                    )
                ).group_by(StickyNote.position_type).all()

                # By symbol (top 10)
                symbol_counts = session.query(
                    StickyNote.symbol,
                    func.count(StickyNote.id),
                ).filter(
                    and_(
                        StickyNote.created_at >= day_start,
                        StickyNote.created_at < day_end,
                        StickyNote.status == "active",
                    )
                ).group_by(StickyNote.symbol).order_by(func.count(StickyNote.id).desc()).limit(10).all()

                return {
                    "total_signals": total,
                    "by_position_type": dict(position_counts),
                    "by_symbol": dict(symbol_counts),
                }

        except Exception as e:
            log.error("Error analyzing signals", error=str(e))
            return {}
