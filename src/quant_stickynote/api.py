"""REST API endpoints for sticky notes service using Bottle framework.

Endpoints:
- GET /health - Health check (always returns 200)
- GET /ready - Readiness check (checks database connection)
- GET /api/sticky-notes - List all signals with filters
- GET /api/sticky-notes/{id} - Get single signal
- PATCH /api/sticky-notes/{id} - Update signal status/notes
- DELETE /api/sticky-notes/{id} - Delete signal
- GET /api/query-executions - Query execution history
- GET /api/stats - Signal statistics

Request/Response Format:
- Content-Type: application/json
- Error responses include error field with message

Example:
    from api import create_app
    app = create_app()
    app.run(host="0.0.0.0", port=8080, quiet=True)
"""
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bottle import Bottle, response, request

from .config import settings
from .database import get_db_health, get_db_session, init_db
from .exceptions import NotFoundError, ValidationError
from .logger import get_logger, log_startup, log_shutdown
from .models import QueryExecution, StickyNote, SignalStatus
from .signal_processor import SignalAnalyzer

log = get_logger(__name__)


def create_app() -> Bottle:
    """Create Bottle application with all endpoints configured.
    
    Returns:
        Bottle app instance
    """
    app = Bottle()

    # Middleware: JSON response headers
    @app.hook("after_request")
    def set_json_headers():
        response.content_type = "application/json"
        response.add_header("X-Service", settings.service_name)
        response.add_header("Access-Control-Allow-Origin", "*")
        response.add_header(
            "Access-Control-Allow-Methods",
            "GET, POST, PUT, PATCH, DELETE, OPTIONS",
        )
        response.add_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    @app.route("/<path:path>", method="OPTIONS")
    def cors_preflight(path: str):
        """Handle browser CORS preflight requests."""
        response.status = 204
        return ""

    # ========================================================================
    # Health & Readiness Endpoints
    # ========================================================================

    @app.get("/health")
    def health_check():
        """Health check endpoint - always returns 200.
        
        Used by load balancers and orchestration to detect liveness.
        Does not perform any checks.
        """
        return {
            "status": "alive",
            "service": settings.service_name,
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        }

    @app.get("/ready")
    def readiness_check():
        """Readiness check endpoint - verifies database connectivity.
        
        Returns:
        - 200 if ready (database connected)
        - 503 if not ready (database down or not initialized)
        """
        health = get_db_health()

        if not health.get("connected"):
            response.status = 503
            return {
                "status": "not_ready",
                "error": health.get("error", "Database not available"),
            }

        return {
            "status": "ready",
            "database": "connected",
            "migration_version": health.get("migration_version"),
            "tables": health.get("tables", {}),
        }

    # ========================================================================
    # Sticky Notes CRUD Endpoints
    # ========================================================================

    @app.get("/api/sticky-notes")
    def list_sticky_notes():
        """List all sticky notes with optional filters.
        
        Query Parameters:
        - status: Filter by status (active, reviewed, cancelled, executed)
        - symbol: Filter by symbol (e.g., AAPL)
        - position_type: Filter by position (LONG, SHORT)
        - limit: Max results (default: 100, max: 1000)
        - offset: Pagination offset (default: 0)
        
        Returns:
            List of StickyNote objects
        """
        try:
            status_filter = request.query.get("status")
            symbol_filter = request.query.get("symbol")
            position_filter = request.query.get("position_type")
            limit = min(int(request.query.get("limit", 100)), 1000)
            offset = int(request.query.get("offset", 0))

            with get_db_session() as session:
                query = session.query(StickyNote)

                if status_filter:
                    query = query.filter(StickyNote.status == status_filter)
                if symbol_filter:
                    query = query.filter(
                        StickyNote.symbol.ilike(f"%{symbol_filter}%")
                    )
                if position_filter:
                    query = query.filter(StickyNote.position_type == position_filter)

                # Order by created_at descending (newest first)
                query = query.order_by(StickyNote.created_at.desc())

                # Count total
                total = query.count()

                # Paginate
                notes = query.offset(offset).limit(limit).all()

                return {
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "results": [note.to_dict() for note in notes],
                }

        except ValueError as e:
            response.status = 400
            return {"error": f"Invalid query parameter: {str(e)}"}
        except Exception as e:
            log.error("Error listing sticky notes", error=str(e))
            response.status = 500
            return {"error": "Failed to list sticky notes"}

    @app.get("/api/sticky-notes/<note_id:int>")
    def get_sticky_note(note_id: int):
        """Get single sticky note by ID.
        
        Returns:
            StickyNote object or 404 if not found
        """
        try:
            with get_db_session() as session:
                note = session.query(StickyNote).filter(
                    StickyNote.id == note_id
                ).first()

                if not note:
                    response.status = 404
                    return {"error": f"Sticky note {note_id} not found"}

                return note.to_dict()

        except Exception as e:
            log.error("Error getting sticky note", note_id=note_id, error=str(e))
            response.status = 500
            return {"error": "Failed to get sticky note"}

    @app.patch("/api/sticky-notes/<note_id:int>")
    def update_sticky_note(note_id: int):
        """Update sticky note status or notes.
        
        Request Body:
        {
            "status": "reviewed|cancelled|executed" (optional),
            "notes": "Updated notes text" (optional)
        }
        
        Returns:
            Updated StickyNote object or 400/404/500 on error
        """
        try:
            data = request.json or {}

            with get_db_session() as session:
                note = session.query(StickyNote).filter(
                    StickyNote.id == note_id
                ).first()

                if not note:
                    response.status = 404
                    return {"error": f"Sticky note {note_id} not found"}

                # Update status if provided
                if "status" in data:
                    new_status = data["status"]
                    valid_statuses = [s.value for s in SignalStatus]
                    if new_status not in valid_statuses:
                        response.status = 400
                        return {
                            "error": f"Invalid status: {new_status}. Must be one of: {valid_statuses}"
                        }

                    old_status = note.status
                    note.status = new_status
                    log.info(
                        "Signal status updated",
                        signal_id=note.id,
                        symbol=note.symbol,
                        old_status=old_status,
                        new_status=new_status,
                    )

                # Update notes if provided
                if "notes" in data:
                    note.notes = data["notes"]

                note.updated_at = datetime.now(timezone.utc)
                session.commit()

                return note.to_dict()

        except json.JSONDecodeError:
            response.status = 400
            return {"error": "Invalid JSON in request body"}
        except Exception as e:
            log.error("Error updating sticky note", note_id=note_id, error=str(e))
            response.status = 500
            return {"error": "Failed to update sticky note"}

    @app.delete("/api/sticky-notes/<note_id:int>")
    def delete_sticky_note(note_id: int):
        """Delete sticky note by ID.
        
        Note: This is a soft-delete - sets status to 'cancelled'.
        
        Returns:
            {"deleted": true} or 404 if not found
        """
        try:
            with get_db_session() as session:
                note = session.query(StickyNote).filter(
                    StickyNote.id == note_id
                ).first()

                if not note:
                    response.status = 404
                    return {"error": f"Sticky note {note_id} not found"}

                note.status = SignalStatus.CANCELLED.value
                note.updated_at = datetime.now(timezone.utc)
                session.commit()

                log.info(
                    "Signal deleted",
                    signal_id=note.id,
                    symbol=note.symbol,
                )

                return {"deleted": True, "note_id": note_id}

        except Exception as e:
            log.error("Error deleting sticky note", note_id=note_id, error=str(e))
            response.status = 500
            return {"error": "Failed to delete sticky note"}

    # ========================================================================
    # Query Execution Audit Endpoints
    # ========================================================================

    @app.get("/api/query-executions")
    def list_query_executions():
        """List query execution history.
        
        Query Parameters:
        - query_id: Filter by query ID
        - status: Filter by status (success, error, skipped)
        - limit: Max results (default: 100, max: 1000)
        - offset: Pagination offset (default: 0)
        
        Returns:
            List of QueryExecution records
        """
        try:
            query_id_filter = request.query.get("query_id")
            status_filter = request.query.get("status")
            limit = min(int(request.query.get("limit", 100)), 1000)
            offset = int(request.query.get("offset", 0))

            with get_db_session() as session:
                query = session.query(QueryExecution)

                if query_id_filter:
                    query = query.filter(QueryExecution.query_id == query_id_filter)
                if status_filter:
                    query = query.filter(QueryExecution.status == status_filter)

                # Order by executed_at descending
                query = query.order_by(QueryExecution.executed_at.desc())

                total = query.count()
                executions = query.offset(offset).limit(limit).all()

                return {
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "results": [exec.to_dict() for exec in executions],
                }

        except ValueError as e:
            response.status = 400
            return {"error": f"Invalid query parameter: {str(e)}"}
        except Exception as e:
            log.error("Error listing query executions", error=str(e))
            response.status = 500
            return {"error": "Failed to list query executions"}

    # ========================================================================
    # Statistics Endpoints
    # ========================================================================

    @app.get("/api/stats")
    def get_stats():
        """Get signal statistics for today.
        
        Returns:
            Aggregated statistics by position type and symbol
        """
        try:
            stats = SignalAnalyzer.get_today_summary()
            return {
                "period": "today",
                "generated_at": datetime.now(timezone.utc).isoformat() + "Z",
                "stats": stats,
            }

        except Exception as e:
            log.error("Error getting statistics", error=str(e))
            response.status = 500
            return {"error": "Failed to get statistics"}

    # ========================================================================
    # Error Handler
    # ========================================================================

    @app.error(404)
    def error_404(err):
        """Handle 404 Not Found."""
        response.content_type = "application/json"
        return {"error": "Endpoint not found"}

    @app.error(405)
    def error_405(err):
        """Handle 405 Method Not Allowed."""
        response.content_type = "application/json"
        return {"error": "Method not allowed"}

    return app


# Application factory
_app_instance: Optional[Bottle] = None


def get_app() -> Bottle:
    """Get or create Bottle application singleton.
    
    Returns:
        Bottle app instance
    """
    global _app_instance
    if _app_instance is None:
        _app_instance = create_app()
    return _app_instance
