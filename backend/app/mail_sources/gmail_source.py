"""Gmail via OAuth (installed-app flow, read-only scope).

One-time setup on your machine (it opens a browser):
    cd backend && .venv/bin/python -m app.mail_sources.gmail_source
This writes secrets/token.json; the backend reuses and refreshes it afterwards.
"""
import base64
import email
from email import policy
from pathlib import Path

from app.mail_sources.base import MailSource, message_to_mail
from app.models import Mail

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def gmail_message_to_mail(msg: dict) -> Mail:
    """Convert a users.messages.get(format="raw") response into a Mail."""
    raw = base64.urlsafe_b64decode(msg["raw"])
    parsed = email.message_from_bytes(raw, policy=policy.default)
    mail = message_to_mail(parsed, msg["id"], thread_id=msg.get("threadId"))
    mail.is_read = "UNREAD" not in msg.get("labelIds", [])
    mail.labels = list(msg.get("labelIds", []))  # e.g. CATEGORY_PROMOTIONS, IMPORTANT
    return mail


class GmailMailSource(MailSource):
    def __init__(self, credentials_path: Path, token_path: Path,
                 max_results: int = 50, query: str = "in:inbox"):
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        self.max_results = max_results
        self.query = query

    def _credentials(self, allow_browser: bool = False):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow

        creds = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
        if creds and creds.valid:
            return creds
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif allow_browser:
            flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)
        else:
            raise RuntimeError("Gmail is not authorized. Run: python -m app.mail_sources.gmail_source")
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(creds.to_json())
        return creds

    def fetch(self, limit: int | None = None) -> list[Mail]:
        from googleapiclient.discovery import build

        service = build("gmail", "v1", credentials=self._credentials(), cache_discovery=False)
        listing = service.users().messages().list(
            userId="me", q=self.query, maxResults=limit or self.max_results
        ).execute()
        mails = []
        for ref in listing.get("messages", []):
            msg = service.users().messages().get(userId="me", id=ref["id"], format="raw").execute()
            mails.append(gmail_message_to_mail(msg))
        return mails


if __name__ == "__main__":
    from app.config import settings

    src = GmailMailSource(settings.gmail_credentials, settings.gmail_token)
    src._credentials(allow_browser=True)
    print(f"Authorized. Token saved to {settings.gmail_token}")
