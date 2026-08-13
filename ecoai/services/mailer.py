"""Outbound email.

Credentials come from the environment. Nothing in this module knows a
password, an address, or a host at import time - the previous implementation
constructed a global SMTP client with a live Gmail app password baked into the
source and printed "Ready to send real emails" the moment anything imported it.

When ``MAIL_ENABLED`` is false the message is rendered and logged instead of
delivered, so development and CI exercise the same code path without needing a
mail server.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr

from ecoai.config import MailConfig

logger = logging.getLogger(__name__)


class MailError(RuntimeError):
    """Raised when a message could not be handed to the SMTP server."""


@dataclass(frozen=True)
class Message:
    to: str
    subject: str
    text_body: str
    html_body: str | None = None


class Mailer:
    """Sends messages over SMTP, or logs them when delivery is disabled."""

    def __init__(self, config: MailConfig) -> None:
        self.config = config

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def send(self, message: Message) -> bool:
        """Deliver a message. Returns True when it was accepted by the server.

        Returns True in disabled mode as well: the caller asked for the message
        to be produced, and it was. Whether a real SMTP hop happened is a
        deployment concern reflected in :attr:`enabled`.
        """
        if not self.config.enabled:
            logger.info(
                "Mail disabled; message not sent",
                extra={"to": message.to, "subject": message.subject},
            )
            return True

        email = self._build(message)
        try:
            self._deliver(email)
        except (smtplib.SMTPException, OSError) as exc:
            logger.error(
                "SMTP delivery failed",
                extra={"to": message.to, "error": str(exc)},
                exc_info=True,
            )
            raise MailError(f"Could not send message to {message.to}") from exc

        logger.info("Message sent", extra={"to": message.to, "subject": message.subject})
        return True

    def _build(self, message: Message) -> EmailMessage:
        email = EmailMessage()
        email["To"] = message.to
        email["From"] = formataddr((self.config.from_name, self.config.from_email))
        email["Subject"] = message.subject
        email.set_content(message.text_body)
        if message.html_body:
            email.add_alternative(message.html_body, subtype="html")
        return email

    def _deliver(self, email: EmailMessage) -> None:
        context = ssl.create_default_context()
        if self.config.port == 465:
            with smtplib.SMTP_SSL(
                self.config.host, self.config.port, context=context, timeout=20
            ) as server:
                server.login(self.config.username, self.config.password)
                server.send_message(email)
            return

        with smtplib.SMTP(self.config.host, self.config.port, timeout=20) as server:
            server.ehlo()
            if self.config.use_tls:
                server.starttls(context=context)
                server.ehlo()
            if self.config.username:
                server.login(self.config.username, self.config.password)
            server.send_message(email)
