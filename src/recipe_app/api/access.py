"""Request IDs and the access log line (ADR-0013 rules 4 and 5).

Pure ASGI, not BaseHTTPMiddleware, which runs the app in another task and
would lose the request ID's context variable on the way.
"""

import asyncio
import logging
import re
import secrets
import time
from uuid import UUID

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from recipe_app.infra.logs import REQUEST_ID

logger = logging.getLogger("recipe_app.access")

REQUEST_ID_HEADER = "X-Request-ID"
# Letters, digits, - and _ only: no space, quote or newline can reach a log line.
_VALID_ID = re.compile(r"[A-Za-z0-9_-]{8,64}")
_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})
UNMATCHED = "unmatched"


class ResponseCutError(Exception):
    """Raised after the response started to have the server drop the
    connection: RequestContext logs the request once and returns, so the
    server closes it with one line instead of a traceback."""


def new_request_id() -> str:
    """A UUIDv7 (RFC 9562): sorts by time, so IDs in a log read in order."""
    millis = time.time_ns() // 1_000_000 & (1 << 48) - 1
    rand = secrets.randbits(74)
    value = (
        millis << 80
        | 0x7 << 76
        | (rand >> 62) << 64
        | 0b10 << 62
        | rand & (1 << 62) - 1
    )
    return str(UUID(int=value))


def current_request_id() -> str | None:
    return REQUEST_ID.get()


class RequestContext:
    """Gives every request an ID and writes one access line when it ends.

    An incoming X-Request-ID that matches `_VALID_ID` is kept, so an ingress
    can stamp one ID from the edge to the pod; any other is replaced. The ID
    goes back in the response header. The line logs the route template, never
    the raw path or query string, so ids and junk URLs can't flood the log.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_id(scope) or new_request_id()
        token = REQUEST_ID.set(request_id)
        request = _Request(scope, request_id)
        _OPEN.add(request)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                request.status = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        failed: str | None = None
        try:
            await self.app(scope, receive, send_with_id)
        except ResponseCutError as error:
            # Whoever raised it logged why. Returning without finishing the
            # response makes the server close the connection.
            failed = type(error).__name__
        except asyncio.CancelledError:
            # The server gave up on the request: the client went away, or the
            # drain after SIGTERM ran out. It still gets its line.
            failed = "cancelled"
            raise
        except Exception as error:
            # Starlette's error middleware sends the 500, after the handler
            # logged the traceback, and then re-raises; the server would log
            # it a second time. Only that case stops here. An error after any
            # other start (a 200 that fails mid-body) goes on to the server,
            # which logs it and drops the connection.
            if request.status != 500:
                failed = type(error).__name__
                raise
        finally:
            request.finish(failed)
            REQUEST_ID.reset(token)


def log_unfinished_requests() -> None:
    """Write the access line of every request still open, as cancelled.

    Called at application shutdown, which uvicorn runs right after it cancels
    the requests that outlived SHUTDOWN_GRACE_SECONDS. A cancelled request
    can take a while to unwind (SQLAlchemy closes its connection politely),
    and the process exits before it does, so without this its line is lost.
    """
    for request in list(_OPEN):
        request.finish("cancelled")


class _Request:
    """One request's access line, written once, whichever path ends it."""

    def __init__(self, scope: Scope, request_id: str) -> None:
        self.scope = scope
        self.request_id = request_id
        self.started = time.perf_counter()
        self.status: int | None = None

    def finish(self, failed: str | None) -> None:
        if self not in _OPEN:
            return
        _OPEN.discard(self)
        token = REQUEST_ID.set(self.request_id)
        try:
            _log_access(
                self.scope, self.status, time.perf_counter() - self.started, failed
            )
        finally:
            REQUEST_ID.reset(token)


_OPEN: set[_Request] = set()


def _incoming_id(scope: Scope) -> str | None:
    for name, value in scope["headers"]:
        if name == b"x-request-id":
            text = value.decode("latin-1")
            return text if _VALID_ID.fullmatch(text) else None
    return None


def _log_access(
    scope: Scope, status: int | None, seconds: float, failed: str | None
) -> None:
    method = scope["method"] if scope["method"] in _METHODS else "OTHER"
    route = getattr(scope.get("route"), "path", None) or UNMATCHED
    duration_ms = round(seconds * 1000, 1)
    shown = "aborted" if status is None or failed else status
    logger.info(
        "%s %s %s %sms",
        method,
        route,
        shown,
        duration_ms,
        extra={
            "fields": {
                "method": method,
                "route": route,
                "status": status,
                "duration_ms": duration_ms,
                **({"error": failed} if failed else {}),
            }
        },
    )
