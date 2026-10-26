"""Read mails from a JSON file (our sample format) or an .mbox export."""
import email
import json
import mailbox
from email import policy
from pathlib import Path

from app.mail_sources.base import MailSource, extract_links, message_to_mail
from app.models import Mail


class FileMailSource(MailSource):
    def __init__(self, path: Path):
        self.path = Path(path)

    def fetch(self, limit: int | None = None) -> list[Mail]:
        if self.path.suffix == ".mbox":
            mails = self._read_mbox()
        else:
            mails = self._read_json()
        mails.sort(key=lambda m: m.received_at, reverse=True)
        return mails[:limit] if limit else mails

    def _read_json(self) -> list[Mail]:
        rows = json.loads(self.path.read_text(encoding="utf-8"))
        return [
            Mail(
                id=r["id"],
                thread_id=r.get("thread_id"),
                sender=r["from"].lower(),
                sender_name=r.get("from_name", ""),
                to=r.get("to", ""),
                subject=r["subject"],
                body=r["body"],
                received_at=r["received_at"],
                is_read=r.get("is_read", False),
                replied=r.get("replied", False),
                headers=r.get("headers", {}),
                labels=r.get("labels", []),
                links=extract_links(r["body"]),
            )
            for r in rows  # the "label" key (ground truth for eval) is ignored here
        ]

    def _read_mbox(self) -> list[Mail]:
        box = mailbox.mbox(
            self.path, factory=lambda f: email.message_from_binary_file(f, policy=policy.default)
        )
        mails = []
        for i, msg in enumerate(box):
            mail_id = str(msg.get("Message-ID", "")).strip("<> ") or f"mbox-{i}"
            mails.append(message_to_mail(msg, mail_id))
        return mails
