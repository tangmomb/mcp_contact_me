from pathlib import Path

import pytest

from mcp_contact_me.auth import BearerAuthMiddleware
from mcp_contact_me.security import TokenRegistry


async def _receive() -> dict:
    return {"type": "http.request", "body": b"", "more_body": False}


def registry_with_token(path: Path, token: str = "x" * 32) -> TokenRegistry:
    registry = TokenRegistry(path)
    registry.import_token("portfolio-ia", token)
    return registry


@pytest.mark.asyncio
async def test_auth_rejects_missing_token(tmp_path: Path) -> None:
    called = False

    async def inner(scope, receive, send) -> None:
        nonlocal called
        called = True

    messages: list[dict] = []

    async def capture(message: dict) -> None:
        messages.append(message)

    middleware = BearerAuthMiddleware(inner, registry_with_token(tmp_path / "tokens.json"))
    await middleware({"type": "http", "headers": []}, _receive, capture)

    assert not called
    assert messages[0]["status"] == 401


@pytest.mark.asyncio
async def test_auth_accepts_valid_project_token(tmp_path: Path) -> None:
    called = False

    async def inner(scope, receive, send) -> None:
        nonlocal called
        called = True

    token = "x" * 32
    middleware = BearerAuthMiddleware(
        inner, registry_with_token(tmp_path / "tokens.json", token)
    )
    await middleware(
        {"type": "http", "headers": [(b"authorization", f"Bearer {token}".encode())]},
        _receive,
        lambda message: None,
    )

    assert called


@pytest.mark.asyncio
async def test_auth_rejects_revoked_token(tmp_path: Path) -> None:
    called = False

    async def inner(scope, receive, send) -> None:
        nonlocal called
        called = True

    async def capture(message: dict) -> None:
        pass

    registry = registry_with_token(tmp_path / "tokens.json")
    registry.revoke("portfolio-ia")
    middleware = BearerAuthMiddleware(inner, registry)
    await middleware(
        {"type": "http", "headers": [(b"authorization", f"Bearer {'x' * 32}".encode())]},
        _receive,
        capture,
    )

    assert not called
