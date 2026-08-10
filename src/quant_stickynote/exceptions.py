"""Custom exceptions for quant_stickynote service."""


class QuoteStickyNoteError(Exception):
    """Base exception for quant_stickynote service."""

    pass


class ConfigurationError(QuoteStickyNoteError):
    """Raised when configuration is invalid or missing."""

    pass


class DatabaseError(QuoteStickyNoteError):
    """Raised when database operations fail."""

    pass


class DatabaseConnectionError(DatabaseError):
    """Raised when unable to connect to database."""

    pass


class QueryExecutionError(QuoteStickyNoteError):
    """Raised when query execution fails."""

    pass


class SignalExtractionError(QuoteStickyNoteError):
    """Raised when signal extraction fails."""

    pass


class ExternalDatabaseError(QuoteStickyNoteError):
    """Raised when external database operations fail."""

    pass


class ExternalDatabaseConnectionError(ExternalDatabaseError):
    """Raised when unable to connect to external database."""

    pass


class QueryDefinitionError(QuoteStickyNoteError):
    """Raised when query definition is invalid."""

    pass


class APIError(QuoteStickyNoteError):
    """Base exception for API errors."""

    pass


class NotFoundError(APIError):
    """Raised when requested resource not found."""

    pass


class ValidationError(APIError):
    """Raised when request validation fails."""

    pass


class TimeoutError(QuoteStickyNoteError):
    """Raised when operation times out."""

    pass


class DuplicateSignalError(QuoteStickyNoteError):
    """Raised when attempting to insert duplicate signal."""

    pass
