import json
from pathlib import Path

import pytest

from mcp_contact_me.security import (
    AuditLogger,
    DeliveryRateLimiter,
    RateLimitExceededError,
    TokenRegistry,
)


def test_registry_hashes_and_revokes_token(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    registry = TokenRegistry(path)
    token = registry.create("portfolio-ia")

    assert token not in path.read_text(encoding="utf-8")
    assert registry.verify_authorization(f"Bearer {token}") == "portfolio-ia"

    registry.revoke("portfolio-ia")
    assert registry.verify_authorization(f"Bearer {token}") is None


def test_rotating_token_invalidates_previous_one(tmp_path: Path) -> None:
    registry = TokenRegistry(tmp_path / "tokens.json")
    old_token = registry.create("portfolio-ia")
    new_token = registry.create("portfolio-ia", replace=True)

    assert registry.verify_authorization(f"Bearer {old_token}") is None
    assert registry.verify_authorization(f"Bearer {new_token}") == "portfolio-ia"


def test_rate_limit_is_persistent_and_per_project(tmp_path: Path) -> None:
    limiter = DeliveryRateLimiter(tmp_path / "limits.db", per_minute=2, per_day=3)
    limiter.check_and_record("project-a", now=1_000)
    limiter.check_and_record("project-a", now=1_001)
    limiter.check_and_record("project-b", now=1_002)

    with pytest.raises(RateLimitExceededError, match="minute"):
        limiter.check_and_record("project-a", now=1_003)

    limiter.check_and_record("project-a", now=1_061)
    with pytest.raises(RateLimitExceededError, match="24 heures"):
        limiter.check_and_record("project-a", now=1_062)


def test_audit_log_excludes_message_and_token(tmp_path: Path) -> None:
    path = tmp_path / "audit.log"
    AuditLogger(path).write(
        project="portfolio-ia",
        channel="email",
        status="sent",
        request_id="request-1",
    )

    event = json.loads(path.read_text(encoding="utf-8"))
    assert event["project"] == "portfolio-ia"
    assert set(event) == {"timestamp", "project", "channel", "status", "request_id"}
