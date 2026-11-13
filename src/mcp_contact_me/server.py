from functools import lru_cache
from typing import Annotated, Literal

import uvicorn
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field

from .auth import BearerAuthMiddleware
from .config import get_settings
from .models import ContactMessage
from .security import (
    AuditLogger,
    DeliveryRateLimiter,
    RateLimitExceededError,
    TokenRegistry,
)
from .services import ContactService

mcp = MCPServer(
    "contact-tanguy",
    instructions=(
        "Utilise ces outils lorsqu'un utilisateur demande à contacter Tanguy au sujet du projet. "
        "N'envoie jamais de message sans une demande explicite de l'utilisateur."
    ),
)


@lru_cache
def get_registry() -> TokenRegistry:
    settings = get_settings()
    return TokenRegistry(settings.token_registry_path)


@lru_cache
def get_rate_limiter() -> DeliveryRateLimiter:
    settings = get_settings()
    return DeliveryRateLimiter(
        settings.rate_limit_db_path,
        settings.rate_limit_per_minute,
        settings.rate_limit_per_day,
    )


@lru_cache
def get_audit_logger() -> AuditLogger:
    return AuditLogger(get_settings().audit_log_path)


def authenticated_project(ctx: Context) -> str:
    headers = ctx.headers or {}
    authorization = headers.get("authorization") or headers.get("Authorization")
    project = get_registry().verify_authorization(authorization)
    if project is None:
        raise ToolError("Authentification requise.")
    return project


async def deliver(
    channel: Literal["email", "telegram"],
    subject: str,
    message: str,
    urgency: Literal["low", "normal", "high"],
    ctx: Context,
) -> dict[str, str]:
    project = authenticated_project(ctx)
    audit = get_audit_logger()
    try:
        get_rate_limiter().check_and_record(project)
    except RateLimitExceededError as exc:
        audit.write(
            project=project,
            channel=channel,
            status="rate_limited",
            request_id=ctx.request_id,
        )
        raise ToolError(str(exc)) from exc

    contact = ContactMessage(
        project=project,
        subject=subject,
        message=message,
        urgency=urgency,
    )
    service = ContactService(get_settings())
    try:
        if channel == "email":
            result = await service.send_email(contact)
        else:
            result = await service.send_telegram(contact)
    except Exception as exc:
        audit.write(
            project=project,
            channel=channel,
            status="failed",
            request_id=ctx.request_id,
            error_type=type(exc).__name__,
        )
        raise ToolError(f"Échec de l'envoi par {channel}.") from exc

    audit.write(
        project=project,
        channel=channel,
        status="sent",
        request_id=ctx.request_id,
    )
    return result


@mcp.tool()
async def send_email(
    subject: Annotated[str, Field(min_length=1, max_length=160)],
    message: Annotated[str, Field(min_length=1, max_length=3500)],
    ctx: Context,
    urgency: Literal["low", "normal", "high"] = "normal",
) -> dict[str, str]:
    """Envoie un e-mail à Tanguy après une demande explicite de l'utilisateur."""
    return await deliver("email", subject, message, urgency, ctx)


@mcp.tool()
async def send_telegram(
    subject: Annotated[str, Field(min_length=1, max_length=160)],
    message: Annotated[str, Field(min_length=1, max_length=3500)],
    ctx: Context,
    urgency: Literal["low", "normal", "high"] = "normal",
) -> dict[str, str]:
    """Envoie un message Telegram à Tanguy après une demande explicite de l'utilisateur."""
    return await deliver("telegram", subject, message, urgency, ctx)


def create_app():
    settings = get_settings()
    registry = get_registry()
    if not any(record["enabled"] for record in registry.list_projects()):
        raise RuntimeError("Aucun jeton de projet actif n'est configuré.")

    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=settings.allowed_hosts,
        allowed_origins=settings.allowed_origins,
    )
    mcp_app = mcp.streamable_http_app(
        host=settings.host,
        transport_security=security,
    )
    return BearerAuthMiddleware(mcp_app, registry)


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        create_app(),
        host=settings.host,
        port=settings.port,
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
    )


if __name__ == "__main__":
    main()
