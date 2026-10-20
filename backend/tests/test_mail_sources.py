import base64
from email.message import EmailMessage

from app.config import ROOT
from app.mail_sources.file_source import FileMailSource
from app.mail_sources.gmail_source import gmail_message_to_mail


def _message(subject="Hello", body="Body text", html=False) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = "Priya Nair <Priya.Nair@Northwind.com>"
    msg["To"] = "sam@example.edu"
    msg["Subject"] = subject
    msg["Date"] = "Tue, 20 Oct 2026 14:30:00 +0530"
    msg["Message-ID"] = "<abc@northwind.com>"
    if html:
        msg.set_content(f"<p>{body}</p><script>x()</script>", subtype="html")
    else:
        msg.set_content(body)
    return msg


def test_sample_json_loads_sorted_newest_first():
    mails = FileMailSource(ROOT / "data" / "sample_mails.json").fetch()
    assert len(mails) >= 50
    assert mails[0].received_at >= mails[-1].received_at
    assert all(m.sender == m.sender.lower() for m in mails)


def test_mbox_source(tmp_path):
    path = tmp_path / "inbox.mbox"
    path.write_bytes(b"From MAILER-DAEMON Thu Jan  1 00:00:00 1970\n" + _message().as_bytes() + b"\n")
    [mail] = FileMailSource(path).fetch()
    assert mail.id == "abc@northwind.com"
    assert mail.sender == "priya.nair@northwind.com"
    assert mail.sender_name == "Priya Nair"
    assert mail.body == "Body text"
    assert mail.received_at.utcoffset().total_seconds() == 5.5 * 3600


def test_gmail_raw_message_parsing_html_and_unread():
    raw = base64.urlsafe_b64encode(_message(body="Interview <b>Thursday</b>", html=True).as_bytes())
    mail = gmail_message_to_mail({"id": "g1", "threadId": "t1", "raw": raw.decode(),
                                  "labelIds": ["INBOX", "UNREAD"]})
    assert mail.id == "g1" and mail.thread_id == "t1"
    assert mail.is_read is False
    assert "Interview Thursday" in mail.body
    assert "x()" not in mail.body
