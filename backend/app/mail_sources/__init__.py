from app.config import settings
from app.mail_sources.base import MailSource
from app.mail_sources.file_source import FileMailSource
from app.mail_sources.gmail_source import GmailMailSource


def get_mail_source() -> MailSource:
    if settings.mail_source == "gmail":
        return GmailMailSource(settings.gmail_credentials, settings.gmail_token, settings.gmail_max)
    return FileMailSource(settings.mail_file)
