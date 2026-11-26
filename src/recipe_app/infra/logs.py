"""One log line per record, JSON by default, on stdout (ADR-0013 rule 4).

Every line written while a request runs carries its request ID, read from a
context variable that the request middleware sets (ADR-0013 rule 5), so no
caller passes it around. A record can carry extra keys in `extra={"fields":
{...}}`; nothing else from the record is copied, so a stray attribute can't
leak into the log.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Literal

type LogFormat = Literal["json", "text"]
type LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]

TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

# Set per request by recipe_app.api.access.RequestContext; None outside one.
REQUEST_ID: ContextVar[str | None] = ContextVar("request_id", default=None)

_APP_LOGGER = "recipe_app"
_SERVER_LOGGER = "uvicorn"


class JsonFormatter(logging.Formatter):
    """time, level, logger, message, request_id, then the record's fields."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "time": _utc(record.created),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = REQUEST_ID.get()
        if request_id is not None:
            entry["request_id"] = request_id
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            for key, value in fields.items():
                entry.setdefault(str(key), value)
        if record.exc_info and record.exc_info[0] is not None:
            entry["exc_type"] = record.exc_info[0].__name__
            entry["traceback"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """Today's readable lines, for local development, plus the request ID."""

    def __init__(self) -> None:
        super().__init__(TEXT_FORMAT)

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        request_id = REQUEST_ID.get()
        return line if request_id is None else f"{line} [{request_id}]"


class _AppHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """Marks the handler this module installed, so a second call adds none."""


def configure_logging(level: LogLevel = "INFO", fmt: LogFormat = "json") -> None:
    """Idempotent: a second call adds no second handler.

    The handler sits on the root logger, so every library's lines (uvicorn,
    SQLAlchemy, asyncpg, FastAPI) come out in the same format. The app and the
    server log at `level`; libraries at WARNING. uvicorn's own handler is
    dropped so its lines reach the root, and its access log is off: the app
    writes one access line per request itself.
    """
    root = logging.getLogger()
    if not any(isinstance(h, _AppHandler) for h in root.handlers):
        handler = _AppHandler(sys.stdout)
        handler.setFormatter(JsonFormatter() if fmt == "json" else TextFormatter())
        root.addHandler(handler)
    root.setLevel(logging.WARNING)

    logging.getLogger(_APP_LOGGER).setLevel(level)
    server = logging.getLogger(_SERVER_LOGGER)
    server.handlers = []
    server.propagate = True
    server.setLevel(level)
    logging.getLogger(f"{_SERVER_LOGGER}.access").disabled = True


def _utc(created: float) -> str:
    stamp = datetime.fromtimestamp(created, UTC).isoformat(timespec="milliseconds")
    return stamp.replace("+00:00", "Z")
