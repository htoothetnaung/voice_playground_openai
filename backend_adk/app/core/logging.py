"""Configures process logging and attaches request IDs so logs can be traced across FastAPI requests."""
from contextvars import ContextVar
import logging

request_id_context: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """Logging filter that injects the current request ID into every emitted log record."""
    def filter(self, record: logging.LogRecord) -> bool:
        """Copy the request ID context variable onto a log record before formatting."""
        record.request_id = request_id_context.get()
        return True


def configure_logging(level: str = "INFO") -> None:
    """Reset root logging and install a formatter that includes the request ID for backend tracing."""
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(request_id)s] %(name)s %(message)s",
    )
    request_id_filter = RequestIdFilter()
    for handler in logging.getLogger().handlers:
        handler.addFilter(request_id_filter)
