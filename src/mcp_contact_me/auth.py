from collections.abc import Awaitable, Callable
from typing import Any

from .security import TokenRegistry

ASGIApp = Callable[
    [dict[str, Any], Callable[[], Awaitable[dict[str, Any]]], Callable[[dict[str, Any]], Awaitable[None]]],
    Awaitable[None],
]


class BearerAuthMiddleware:
    """Bloque les requêtes HTTP dont le jeton n'identifie pas un projet actif."""

    def __init__(self, app: ASGIApp, registry: TokenRegistry) -> None:
        self.app = app
        self.registry = registry

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {name.lower(): value for name, value in scope.get("headers", [])}
        try:
            authorization = headers.get(b"authorization", b"").decode("ascii")
        except UnicodeDecodeError:
            authorization = ""

        if self.registry.verify_authorization(authorization) is None:
            body = b'{"error":"unauthorized"}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                        (b"www-authenticate", b'Bearer realm="mcp-contact-me"'),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, send)
