"""The request deadline and the concurrency limit (ADR-0013 rule 7).

Both answer with the same 503 problem as an unavailable database (rule 1).
Both are pure ASGI: BaseHTTPMiddleware runs the app in another task, which
gets cancellation wrong. Liveness (/healthz) skips both, so a busy pod is
never killed for being busy.
"""

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from starlette.routing import BaseRoute, Match
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from recipe_app.api.access import ResponseCutError
from recipe_app.api.problems import DEFAULT_RETRY_AFTER_SECONDS, service_unavailable

logger = logging.getLogger(__name__)

EXEMPT_PATHS = frozenset({"/healthz"})


@dataclass(frozen=True, slots=True)
class Guards:
    """The limits, from settings in production and defaults in tests."""

    request_timeout: float = 8
    max_in_flight: int = 64
    retry_after: int = DEFAULT_RETRY_AFTER_SECONDS


class DeadlineExceededError(ResponseCutError):
    """The deadline passed after the response had started, so no 503 can be
    sent; the connection is dropped instead."""


class RequestDeadline:
    """Cancels a request still running after `seconds`.

    Before the response has started the client gets the 503. After, the
    status line is already out, so the only honest signal left is to close
    the connection: the client sees a cut response, never a "200" that
    silently stopped. A query cancelled this way leaves its connection in an
    unknown state; SQLAlchemy discards it rather than reuse it.
    """

    def __init__(self, app: ASGIApp, seconds: float, retry_after: int) -> None:
        self.app = app
        self.seconds = seconds
        self.retry_after = retry_after

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        deadline = asyncio.timeout(self.seconds)
        try:
            async with deadline:
                await self.app(scope, receive, tracking_send)
        except TimeoutError:
            # A TimeoutError the app raised itself is not ours to answer.
            if not deadline.expired():
                raise
            logger.warning("request deadline of %gs exceeded", self.seconds)
            if started:
                raise DeadlineExceededError from None
            await service_unavailable(self.retry_after)(scope, receive, send)


class ConcurrencyLimit:
    """At most `limit` requests run at once in this process; one more gets the
    503 straight away instead of queueing until every request is slow.

    One event loop per process, so a plain counter is safe: nothing awaits
    between the check and the increment.

    A shed request never reaches the router, so the limit finds its route
    itself: the access line names it, and a dashboard counts shedding per
    route instead of as "unmatched" traffic. Only shed requests pay for it.
    """

    def __init__(
        self,
        app: ASGIApp,
        limit: int,
        retry_after: int,
        routes: Sequence[BaseRoute] = (),
    ) -> None:
        self.app = app
        self.limit = limit
        self.retry_after = retry_after
        self.routes = routes
        self.in_flight = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        if self.in_flight >= self.limit:
            logger.warning("%d requests already in flight; shedding", self.in_flight)
            route = next(
                (r for r in self.routes if r.matches(scope)[0] is Match.FULL), None
            )
            if route is not None:
                scope["route"] = route
            await service_unavailable(self.retry_after)(scope, receive, send)
            return

        self.in_flight += 1
        try:
            await self.app(scope, receive, send)
        finally:
            self.in_flight -= 1
