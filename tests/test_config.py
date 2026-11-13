from mcp_contact_me.config import Settings


def test_allowed_hosts_accepts_comma_separated_env(monkeypatch) -> None:
    monkeypatch.setenv(
        "CONTACT_ALLOWED_HOSTS",
        "127.0.0.1:*, localhost:*, MCP.EXAMPLE.COM",
    )

    settings = Settings(_env_file=None)

    assert settings.allowed_hosts == [
        "127.0.0.1:*",
        "localhost:*",
        "mcp.example.com",
    ]
