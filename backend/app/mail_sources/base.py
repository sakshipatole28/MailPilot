"""MailSource interface + a helper that turns an RFC 822 message into a Mail."""
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr, parsedate_to_datetime

from app.models import Mail


class MailSource(ABC):
    @abstractmethod
    def fetch(self, limit: int | None = None) -> list[Mail]:
        """Return mails, newest first."""


def _html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", "", html)
    text = re.sub(r"(?i)<br\s*/?>|</p>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def message_to_mail(msg: EmailMessage, mail_id: str, thread_id: str | None = None) -> Mail:
    """Parse a message created with policy=email.policy.default (needed for get_body)."""
    name, addr = parseaddr(str(msg.get("From", "")))
    try:
        received = parsedate_to_datetime(str(msg["Date"]))
    except (TypeError, ValueError):
        received = datetime.now(timezone.utc)

    body = ""
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is not None:
        body = part.get_content()
        if part.get_content_type() == "text/html":
            body = _html_to_text(body)

    return Mail(
        id=mail_id,
        thread_id=thread_id,
        sender=addr.lower(),
        sender_name=name,
        to=str(msg.get("To", "")),
        subject=str(msg.get("Subject", "(no subject)")),
        body=body.strip(),
        received_at=received,
    )
