"""Query engine for loading and executing signal detection queries.

Loads JSON query definitions from queries/ directory and executes them
against external databases.

Query Definition Structure:
{
  "id": "unique_id",
  "name": "Human readable name",
  "enabled": true/false,
  "symbol_query": "SELECT symbol FROM ...",
  "price_query": "SELECT symbol, price FROM ... WHERE symbol = :symbol",
  "signal_extraction": {
    "symbol_column": "symbol",
    "buy_price_column": "price"
  },
  "dedup_key_ttl_hours": 24,
  "timeout_seconds": 300
}
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from .config import settings
from .logger import get_logger

log = get_logger(__name__)

# Queries directory (QUERIES_DIR env var; relative paths resolve against CWD)
QUERIES_DIR = Path(settings.queries_dir)


class QueryDefinition:
    """Represents a single query definition from JSON file.
    
    Attributes:
        id: Unique query identifier
        name: Human readable name
        enabled: Whether query is enabled
        symbol_query: SQL query to get candidate symbols
        price_query: SQL query to get price for each symbol
        signal_extraction: How to parse results
        dedup_key_ttl_hours: Dedup TTL
        timeout_seconds: Query timeout
    """

    def __init__(self, definition: Dict[str, Any]):
        """Initialize from query definition dictionary.
        
        Args:
            definition: Parsed JSON query definition
            
        Raises:
            ValueError: If definition is invalid
        """
        self.id = definition.get("id")
        self.name = definition.get("name")
        self.enabled = definition.get("enabled", True)
        self.symbol_query = definition.get("symbol_query")
        self.price_query = definition.get("price_query")
        self.signal_extraction = definition.get("signal_extraction", {})
        self.dedup_key_ttl_hours = definition.get("dedup_key_ttl_hours", 24)
        self.timeout_seconds = definition.get("timeout_seconds", 300)

        self._validate()

    def _validate(self) -> None:
        """Validate query definition.
        
        Raises:
            ValueError: If any required field is missing or invalid
        """
        if not self.id:
            raise ValueError("Query definition missing 'id' field")
        if not self.name:
            raise ValueError(f"Query {self.id} missing 'name' field")
        if not self.symbol_query:
            raise ValueError(f"Query {self.id} missing 'symbol_query' field")
        if not self.price_query:
            raise ValueError(f"Query {self.id} missing 'price_query' field")

        signal_ext = self.signal_extraction
        if not signal_ext.get("symbol_column"):
            raise ValueError(f"Query {self.id} missing signal_extraction.symbol_column")
        if not signal_ext.get("buy_price_column"):
            raise ValueError(f"Query {self.id} missing signal_extraction.buy_price_column")

    def get_symbol_column(self) -> str:
        """Get column name for stock symbol."""
        return self.signal_extraction.get("symbol_column", "symbol")

    def get_buy_price_column(self) -> str:
        """Get column name for buy price."""
        return self.signal_extraction.get("buy_price_column", "price")

    def get_trigger_reason_template(self) -> str:
        """Get trigger reason template or default to query name."""
        return self.name


class QueryEngine:
    """Manages loading and execution of query definitions."""

    def __init__(self, queries_dir: Optional[Path] = None):
        """Initialize query engine.
        
        Args:
            queries_dir: Path to queries directory (default: QUERIES_DIR)
        """
        self.queries_dir = queries_dir or QUERIES_DIR
        self.queries: Dict[str, QueryDefinition] = {}
        self.load_queries()

    def load_queries(self) -> None:
        """Load all query definitions from queries/ directory.
        
        Reads all .json files and validates them.
        Logs any errors but continues loading.
        """
        if not self.queries_dir.exists():
            log.warning("Queries directory not found", path=str(self.queries_dir))
            return

        for json_file in self.queries_dir.glob("*.json"):
            try:
                with open(json_file) as f:
                    definition = json.load(f)
                    query_def = QueryDefinition(definition)
                    self.queries[query_def.id] = query_def
                    log.info(
                        "Query loaded",
                        query_id=query_def.id,
                        enabled=query_def.enabled,
                    )
            except (json.JSONDecodeError, ValueError) as e:
                log.error(
                    "Failed to load query",
                    file=str(json_file),
                    error=str(e),
                )

    def get_query(self, query_id: str) -> Optional[QueryDefinition]:
        """Get query by ID.
        
        Args:
            query_id: Query identifier
            
        Returns:
            QueryDefinition or None if not found
        """
        return self.queries.get(query_id)

    def get_enabled_queries(self) -> List[QueryDefinition]:
        """Get all enabled queries.
        
        Returns:
            List of enabled query definitions
        """
        return [q for q in self.queries.values() if q.enabled]

    def execute_query(
        self, query: QueryDefinition
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Execute a symbol query and a separate price query, then extract signals.
        
        Args:
            query: QueryDefinition to execute
            
        Returns:
            Tuple of (signals, error_message):
            - signals: List of signal dictionaries
            - error_message: Error message if failed, None if successful
            
        Note:
            Returns empty list + error message on failure,
            never raises exceptions (logs and continues)
        """
        try:
            # Get database URL from settings (environment)
            db_url = settings.database_url

            # Rewrite dialect for psycopg3 if needed
            if db_url.startswith("postgresql://") or db_url.startswith("postgres://"):
                db_url = db_url.replace("://", "+psycopg://", 1)

            # Create engine for external database; NullPool avoids leaked idle connections
            engine = create_engine(
                db_url,
                poolclass=NullPool,
            )

            with engine.connect() as connection:
                symbol_rows = connection.execute(text(query.symbol_query)).fetchall()
                signals = []

                for symbol_row in symbol_rows:
                    row_dict = dict(symbol_row._mapping) if hasattr(symbol_row, "_mapping") else dict(symbol_row)
                    symbol = row_dict.get(query.get_symbol_column())
                    if symbol is None:
                        continue

                    price_rows = connection.execute(
                        text(query.price_query),
                        {"symbol": str(symbol)},
                    ).fetchall()

                    for price_row in price_rows:
                        price_dict = dict(price_row._mapping) if hasattr(price_row, "_mapping") else dict(price_row)
                        signal = self._extract_signal(query, price_dict)
                        if signal is not None:
                            signals.append(signal)

            return signals, None

        except SQLAlchemyError as e:
            error_msg = f"Database error: {str(e)}"
            log.error(
                "Query execution failed",
                query_id=query.id,
                error_type="SQLAlchemyError",
                error=str(e),
            )
            return [], error_msg

        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            log.error(
                "Query execution failed",
                query_id=query.id,
                error_type=type(e).__name__,
                error=str(e),
            )
            return [], error_msg

    def _extract_signal(
        self, query: QueryDefinition, row_dict: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Extract a single signal from a price-row dictionary."""
        try:
            symbol = row_dict.get(query.get_symbol_column())
            buy_price = row_dict.get(query.get_buy_price_column())

            if not symbol or buy_price is None:
                return None

            position_type = "LONG"

            return {
                "symbol": str(symbol),
                "buy_price": float(buy_price),
                "position_type": position_type,
                "trigger_reason": query.get_trigger_reason_template(),
                "source_query_id": query.id,
            }
        except Exception as e:
            log.warning(
                "Error extracting signal from row",
                query_id=query.id,
                error=str(e),
            )
            return None


# Global query engine instance
_engine_instance: Optional[QueryEngine] = None


def get_query_engine() -> QueryEngine:
    """Get or create query engine singleton.
    
    Returns:
        QueryEngine instance
    """
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = QueryEngine()
    return _engine_instance
