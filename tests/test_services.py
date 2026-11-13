from unittest.mock import MagicMock, patch

import pytest

from mcp_contact_me.config import Settings
from mcp_contact_me.models import ContactMessage
from mcp_contact_me.services import ChannelNotConfiguredError, ContactService


@pytest.fixture
def contact() -> ContactMessage:
    return ContactMessage(project="Test", subject="Bonjour", message="Message")


@pytest.mark.asyncio
async def test_email_requires_configuration(contact: ContactMessage) -> None:
    service = ContactService(Settings(_env_file=None))

    with pytest.raises(ChannelNotConfiguredError):
        await service.send_email(contact)


@pytest.mark.asyncio
async def test_telegram_posts_to_fixed_chat(contact: ContactMessage) -> None:
    settings = Settings(
        _env_file=None,
        telegram_bot_token="secret-token",
        telegram_chat_id="12345",
    )
    response = MagicMock()
    response.read.return_value = b'{"ok": true}'
    response.__enter__.return_value = response

    with patch("mcp_contact_me.services.urlopen", return_value=response) as mocked_urlopen:
        result = await ContactService(settings).send_telegram(contact)

    request = mocked_urlopen.call_args.args[0]
    assert request.full_url == "https://api.telegram.org/botsecret-token/sendMessage"
    assert b"chat_id=12345" in request.data
    assert result["status"] == "sent"
