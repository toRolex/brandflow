"""Log service for persistent error logging."""

from packages.log_service.log_writer import get_log_dir, log_error

__all__ = ["get_log_dir", "log_error"]
