"""Security headers on every response the API sends.

The API serves JSON only, so its Content-Security-Policy allows nothing: a
response that a browser somehow renders as a page can't run script, load
anything or be framed. HSTS is not set here; the TLS edge in front of the
API sets it, because only that layer knows the request came over HTTPS.
"""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

API_CSP = (
    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)

SECURITY_HEADERS = {
    "Content-Security-Policy": API_CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
}

# Swagger UI and ReDoc are HTML pages that load their scripts from a CDN and
# run inline script, so the API's policy would leave them blank. They are
# served only when API_DOCS is on, which is local development only.
DOCS_PAGES = frozenset({"/docs", "/docs/oauth2-redirect", "/redoc"})


class SecurityHeaders:
    """Adds `SECURITY_HEADERS` to each response, keeping any a route set itself.

    Paths in `pages_without_csp` get every header but the CSP.
    """

    def __init__(
        self, app: ASGIApp, pages_without_csp: frozenset[str] = frozenset()
    ) -> None:
        self.app = app
        self.pages_without_csp = pages_without_csp

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        skip_csp = scope["path"] in self.pages_without_csp

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    if skip_csp and name == "Content-Security-Policy":
                        continue
                    headers.setdefault(name, value)
            await send(message)

        await self.app(scope, receive, send_with_headers)
