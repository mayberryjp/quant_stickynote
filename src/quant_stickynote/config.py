"""Configuration management for quant_stickynote service.

Uses Pydantic BaseSettings to read environment variables with type validation.
Configuration is loaded once at startup and exposed as a singleton instance.

Environment variables can be:
1. Set via .env file (python-dotenv)
2. Set via shell environment (export KEY=value)
3. Set via Docker environment
4. Set via supervisord/systemd configs

Example usage:
    from config import settings
    
    engine = create_engine(settings.database_url)
    app.run(host=settings.api_host, port=settings.api_port)
"""
from datetime import time
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuration settings for quant_stickynote service.
    
    All settings read from environment variables. Supports .env file
    for local overrides (python-dotenv reads .env automatically).
    
    Attributes:
        service_name: Service identifier for logging
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        
        database_url: PostgreSQL connection string for sticky notes storage
        database_pool_size: Connection pool size (default: 5)
        database_pool_recycle_seconds: Connection recycle time (default: 3600)
        database_pool_pre_ping: Enable pre-ping for connection health (default: True)
        
        trigger_time: Time (UTC, HH:MM) to execute queries
        check_interval_seconds: How often to check if trigger time reached
        
        api_host: Host to bind API server to
        api_port: Port for REST API
        api_workers: Number of Waitress worker threads
        
        worker_enabled: Enable background worker daemon
        worker_log_every_n_cycles: Log worker status every N cycles
        
        data_warehouse_url: Optional external database for query data
        options_analysis_url: Optional external database for options data
        historical_data_url: Optional external database for price history
        insider_data_url: Optional external database for insider data
    """

    # Service Configuration
    service_name: str = "quant_stickynote"
    log_level: str = "INFO"

    # Database Configuration
    database_url: str
    database_pool_size: int = 5
    database_pool_recycle_seconds: int = 3600
    database_pool_pre_ping: bool = True

    # Scheduling Configuration
    trigger_time: str = "09:30"  # HH:MM format (UTC)
    check_interval_seconds: int = 60

    # Query Configuration
    queries_dir: str = "queries"

    # API Server Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    api_workers: int = 20

    # Worker Daemon Configuration
    worker_enabled: bool = True
    worker_log_every_n_cycles: int = 10

    # External Database URLs (Optional)
    data_warehouse_url: Optional[str] = None
    options_analysis_url: Optional[str] = None
    historical_data_url: Optional[str] = None
    insider_data_url: Optional[str] = None

    class Config:
        """Pydantic configuration for BaseSettings."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    @property
    def trigger_time_parsed(self) -> time:
        """Parse trigger_time string (HH:MM) to datetime.time object.
        
        Returns:
            time: Parsed time object (e.g., time(9, 30) for "09:30")
            
        Raises:
            ValueError: If trigger_time format is invalid
        """
        try:
            parts = self.trigger_time.split(":")
            if len(parts) != 2:
                raise ValueError(
                    f"trigger_time must be HH:MM format, got '{self.trigger_time}'"
                )
            hour = int(parts[0])
            minute = int(parts[1])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError(
                    f"trigger_time hours must be 0-23 and minutes 0-59, "
                    f"got {hour}:{minute:02d}"
                )
            return time(hour, minute)
        except (ValueError, AttributeError) as e:
            raise ValueError(
                f"Failed to parse trigger_time '{self.trigger_time}': {e}"
            ) from e

    def get_external_database_url(self, source_name: str) -> Optional[str]:
        """Get external database URL by source name.
        
        Args:
            source_name: Name of external database (e.g., "data_warehouse")
            
        Returns:
            Database URL if configured, None otherwise
            
        Example:
            url = settings.get_external_database_url("data_warehouse")
            if url:
                engine = create_engine(url)
        """
        attr_name = f"{source_name.lower()}_url"
        return getattr(self, attr_name, None)

    def validate_for_worker(self) -> None:
        """Validate configuration for worker daemon.
        
        Raises:
            ValueError: If configuration is invalid for worker mode
        """
        if not self.database_url:
            raise ValueError("DATABASE_URL is required for worker daemon")
        if not self.trigger_time:
            raise ValueError("TRIGGER_TIME is required for worker daemon")
        try:
            self.trigger_time_parsed
        except ValueError as e:
            raise ValueError(f"Invalid TRIGGER_TIME: {e}") from e

    def validate_for_api(self) -> None:
        """Validate configuration for API server.
        
        Raises:
            ValueError: If configuration is invalid for API mode
        """
        if not self.database_url:
            raise ValueError("DATABASE_URL is required for API server")
        if not (1 <= self.api_port <= 65535):
            raise ValueError(f"API_PORT must be 1-65535, got {self.api_port}")
        if self.api_workers < 1:
            raise ValueError(f"API_WORKERS must be >= 1, got {self.api_workers}")


# Load configuration once at module import time
settings = Settings()
