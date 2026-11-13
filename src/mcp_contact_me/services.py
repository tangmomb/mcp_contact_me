import asyncio
import json
import smtplib
import ssl
from email.message import EmailMessage
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import Settings
from .models import ContactMessage


class ChannelNotConfiguredError(RuntimeError):
    pass


class DeliveryError(RuntimeError):
    pass


class ContactService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send_email(self, contact: ContactMessage) -> dict[str, str]:
        self._validate_email_configuration()
        await asyncio.to_thread(self._send_email_sync, contact)
        return {"status": "sent", "channel": "email", "project": contact.project}

    async def send_telegram(self, contact: ContactMessage) -> dict[str, str]:
        self._validate_telegram_configuration()
        await asyncio.to_thread(self._send_telegram_sync, contact)
        return {"status": "sent", "channel": "telegram", "project": contact.project}

    def _validate_email_configuration(self) -> None:
        required = {
            "CONTACT_SMTP_HOST": self.settings.smtp_host,
            "CONTACT_EMAIL_FROM": self.settings.email_from,
            "CONTACT_EMAIL_TO": self.settings.email_to,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ChannelNotConfiguredError(
                "Canal e-mail non configuré. Variables manquantes : " + ", ".join(missing)
            )

    def _validate_telegram_configuration(self) -> None:
        if not self.settings.telegram_bot_token or not self.settings.telegram_chat_id:
            raise ChannelNotConfiguredError(
                "Canal Telegram non configuré. Définir CONTACT_TELEGRAM_BOT_TOKEN "
                "et CONTACT_TELEGRAM_CHAT_ID."
            )

    def _send_email_sync(self, contact: ContactMessage) -> None:
        email = EmailMessage()
        email["From"] = self.settings.email_from
        email["To"] = self.settings.email_to
        email["Subject"] = f"[{contact.project}] {contact.subject}"
        email.set_content(contact.formatted_body())

        try:
            if self.settings.smtp_security == "ssl":
                smtp_factory = smtplib.SMTP_SSL
            else:
                smtp_factory = smtplib.SMTP

            with smtp_factory(
                self.settings.smtp_host,
                self.settings.smtp_port,
                timeout=20,
            ) as smtp:
                if self.settings.smtp_security == "starttls":
                    smtp.starttls(context=ssl.create_default_context())
                if self.settings.smtp_username:
                    password = (
                        self.settings.smtp_password.get_secret_value()
                        if self.settings.smtp_password
                        else ""
                    )
                    smtp.login(self.settings.smtp_username, password)
                smtp.send_message(email)
        except (OSError, smtplib.SMTPException) as exc:
            raise DeliveryError(f"Échec de l'envoi SMTP : {exc}") from exc

    def _send_telegram_sync(self, contact: ContactMessage) -> None:
        token = self.settings.telegram_bot_token.get_secret_value()  # type: ignore[union-attr]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = urlencode(
            {
                "chat_id": self.settings.telegram_chat_id,
                "text": contact.formatted_body(),
                "disable_web_page_preview": "true",
            }
        ).encode("utf-8")
        request = Request(url, data=payload, method="POST")

        try:
            with urlopen(request, timeout=20) as response:  # noqa: S310 - URL fixe Telegram
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise DeliveryError(f"Telegram a refusé le message ({exc.code}) : {detail}") from exc
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise DeliveryError(f"Échec de l'envoi Telegram : {exc}") from exc

        if not result.get("ok"):
            raise DeliveryError(f"Telegram a retourné une erreur : {result}")
