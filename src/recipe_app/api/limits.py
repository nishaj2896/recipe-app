"""A cap on request body size, checked before any route parses the body."""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from recipe_app.api.problems import problem_response
from recipe_app.api.schemas import Problem

# The largest valid search (50 ids, 100 staples, 200 hidden ids and a cursor)
# is about 20 KB of JSON, so 64 KiB leaves room without letting a client make
# a pod read and parse megabytes just to send back a 422.
MAX_BODY_BYTES = 64 * 1024


class BodySizeLimit:
    """Sends 413 for a body over `max_bytes`, declared or streamed.

    The body is read here, up to the cap, and replayed to the app, so a client
    that sends no Content-Length (or a wrong one) is capped the same way.
    """

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = _content_length(scope)
        if declared is not None and declared > self.max_bytes:
            await self._too_large(scope, receive, send)
            return

        messages: list[Message] = []
        size = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] != "http.request":
                break
            size += len(message.get("body", b""))
            if size > self.max_bytes:
                await self._too_large(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        async def replay() -> Message:
            return messages.pop(0) if messages else await receive()

        await self.app(scope, replay, send)

    async def _too_large(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = problem_response(
            Problem(
                title="Content Too Large",
                status=413,
                detail=f"The request body must be at most {self.max_bytes} bytes.",
            )
        )
        # The rest of the body is never read, so the connection can't be reused.
        response.headers["Connection"] = "close"
        await response(scope, receive, send)


def _content_length(scope: Scope) -> int | None:
    for name, value in scope["headers"]:
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None
