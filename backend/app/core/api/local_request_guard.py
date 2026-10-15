"""Keep the unauthenticated local API reachable only from this machine's own pages.

Genesis has no accounts, so a request is trusted because of where it comes from. This
guard enforces two things for every HTTP request and WebSocket handshake:

1. **Host.** The ``Host`` header must name a trusted loopback host (``localhost``,
   ``127.0.0.1``, ``[::1]``; any port). This defeats DNS rebinding, where a website makes
   its own domain resolve to 127.0.0.1 and then calls the API as if it were same-origin.

2. **Origin.** Browsers send ``Origin`` with every state-changing request, including the
   bodiless cross-site POSTs that CORS does not stop. A state-changing request or a
   WebSocket handshake that carries an ``Origin`` must come from a configured frontend
   origin or from the backend itself (its ``/docs`` page); ``Origin: null`` is refused.
   Requests without ``Origin`` are allowed: they come from non-browser clients (curl,
   scripts, tests), unless the browser-only ``Sec-Fetch-Site`` header says cross-site.

This is not authentication. Any program already running on this machine can call the
API, and anything that can reach the port can read GET endpoints.
"""

from collections.abc import Callable, Iterable

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def host_name(header: str | None) -> str | None:
    """The host part of a Host header, lowercased, without port or IPv6 brackets."""
    if not header:
        return None
    value = header.strip().lower()
    if value.startswith("["):
        end = value.find("]")
        host, rest = (value[1:end], value[end + 1:]) if end > 1 else ("", "")
        if not host or (rest and not (rest.startswith(":") and rest[1:].isdigit())):
            return None
        return host
    host, separator, port = value.partition(":")
    if not host or (separator and not port.isdigit()):
        return None
    return host


def _normalized_hosts(hosts: Iterable[str]) -> set[str]:
    return {name for name in (host_name(host) for host in hosts) if name is not None}


def _normalized_origin(origin: str) -> str:
    return origin.strip().lower().rstrip("/")


class LocalRequestGuard:
    def __init__(
        self,
        app: ASGIApp,
        *,
        trusted_hosts: Callable[[], Iterable[str]],
        trusted_origins: Callable[[], Iterable[str]],
    ) -> None:
        # Read on every request, so configuration (and test isolation) applies immediately.
        self.app = app
        self._trusted_hosts = trusted_hosts
        self._trusted_origins = trusted_origins

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        host_header = headers.get("host")
        if host_name(host_header) not in _normalized_hosts(self._trusted_hosts()):
            await self._refuse(scope, receive, send, 400, "Untrusted Host header.")
            return
        changes_state = scope["type"] == "websocket" or scope["method"] not in SAFE_METHODS
        if changes_state and not self._origin_trusted(scope, headers, host_header or ""):
            await self._refuse(scope, receive, send, 403, "Requests from this origin are not allowed.")
            return
        await self.app(scope, receive, send)

    def _origin_trusted(self, scope: Scope, headers: Headers, host_header: str) -> bool:
        origin = headers.get("origin")
        if origin is None:
            # Not a browser request, unless the browser says it is a cross-site one.
            return headers.get("sec-fetch-site") != "cross-site"
        origin = _normalized_origin(origin)
        if origin in {_normalized_origin(item) for item in self._trusted_origins()}:
            return True
        scheme = "https" if scope.get("scheme") in {"https", "wss"} else "http"
        return origin == f"{scheme}://{host_header.strip().lower()}"  # the backend's own pages

    @staticmethod
    async def _refuse(scope: Scope, receive: Receive, send: Send, status_code: int, detail: str) -> None:
        if scope["type"] == "websocket":
            # Closing before accepting makes the server answer the handshake with HTTP 403.
            await send({"type": "websocket.close", "code": 1008, "reason": detail})
            return
        await JSONResponse({"detail": detail}, status_code=status_code)(scope, receive, send)
