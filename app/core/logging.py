import json
import logging
import sys
from datetime import datetime, timezone

from app.core.correlation import (
    get_correlation_id,
)


class CorrelationIdFilter(logging.Filter):
    """
    Add the current correlation ID to every LogRecord.
    """

    def filter(
        self,
        record: logging.LogRecord,
    ) -> bool:
        record.correlation_id = (
            get_correlation_id()
        )

        return True


class JsonFormatter(logging.Formatter):
    """
    Format application logs as one JSON object per line.
    """

    def format(
        self,
        record: logging.LogRecord,
    ) -> str:
        log_data = {
            "timestamp": datetime.fromtimestamp(
                record.created,
                tz=timezone.utc,
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "correlation_id": getattr(
                record,
                "correlation_id",
                "-",
            ),
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_data["exception"] = (
                self.formatException(
                    record.exc_info
                )
            )

        return json.dumps(
            log_data,
            default=str,
        )


def configure_logging() -> None:
    """
    Configure application logging to stdout as JSON.
    """

    handler = logging.StreamHandler(
        sys.stdout
    )

    handler.setFormatter(
        JsonFormatter()
    )

    handler.addFilter(
        CorrelationIdFilter()
    )

    root_logger = logging.getLogger()

    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

    # Route Uvicorn logging through the same JSON handler.
    for logger_name in (
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
    ):
        uvicorn_logger = logging.getLogger(
            logger_name
        )

        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True


def get_logger(
    name: str,
) -> logging.Logger:
    return logging.getLogger(name)