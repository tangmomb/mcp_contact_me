import pytest
from pydantic import ValidationError

from mcp_contact_me.models import ContactMessage


def test_contact_message_formats_body() -> None:
    contact = ContactMessage(
        project="Portfolio IA",
        subject="Prise de contact",
        message="Bonjour Tanguy",
        urgency="high",
    )

    assert "Projet : Portfolio IA" in contact.formatted_body()
    assert "Urgence : high" in contact.formatted_body()


@pytest.mark.parametrize("field", ["project", "subject"])
def test_contact_message_rejects_header_injection(field: str) -> None:
    values = {"project": "Projet", "subject": "Sujet", "message": "Message"}
    values[field] = "valeur\nX-Injected: yes"

    with pytest.raises(ValidationError):
        ContactMessage(**values)
