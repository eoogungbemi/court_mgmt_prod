"""
Structured JSON logging for production; coloured plain text for development.
Call configure_logging() once at application startup.
"""

import logging
import sys
import json
import time
from contextvars import ContextVar
from config import ENVIRONMENT

# Thread/async-safe storage for the current request ID
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log: dict = {
            "ts":         self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level":      record.levelname,
            "logger":     record.name,
            "request_id": request_id_var.get("-"),
            "msg":        record.getMessage(),
        }
        if record.exc_info:
            log["exc"] = self.formatException(record.exc_info)
        return json.dumps(log)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    if ENVIRONMENT == "production":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s  %(levelname)-8s  %(name)s  [%(request_id)s]  %(message)s",
                datefmt="%H:%M:%S",
            )
        )
    # Inject request_id into every LogRecord so the plain formatter can use it
    old_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        record.request_id = request_id_var.get("-")  # type: ignore[attr-defined]
        return record

    logging.setLogRecordFactory(record_factory)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    # Quiet noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
