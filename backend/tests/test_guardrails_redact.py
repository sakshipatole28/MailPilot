import logging

from app.llm.guardrails import check_draft
from app.redact import RedactingFilter, redact

SOURCE = "Interview on Thursday 22 October at 11:00 AM. Link: https://meet.google.com/abc. Hi Sam"


def test_supported_facts_pass_unchanged():
    draft = "Hi Sam, Thursday 22 October at 11:00 AM works. Link: https://meet.google.com/abc"
    result = check_draft(draft, SOURCE)
    assert result.text == draft
    assert result.issues == []


def test_unsupported_facts_become_placeholders():
    draft = "Can we do 5 November at 3 PM instead? My number is +91 98765 43210, see www.x.io"
    result = check_draft(draft, SOURCE)
    assert "[confirm: 5 November]" in result.text
    assert "[confirm: 3 PM]" in result.text
    assert "[confirm: +91 98765 43210]" in result.text
    assert "[confirm: www.x.io]" in result.text
    assert len(result.issues) == 4


def test_time_inside_date_is_not_double_wrapped():
    result = check_draft("See you at 5:30 pm", SOURCE)
    assert result.text == "See you at [confirm: 5:30 pm]"


def test_ordinal_dates_match_source():
    assert check_draft("Thanks, see you on 22nd October.", SOURCE).issues == []


def test_greeting_name_must_exist():
    result = check_draft("Dear Rohan,\nThanks.", SOURCE)
    assert result.text.startswith("Dear [name],")
    assert result.issues


def test_redact():
    text = "Mail from priya.nair@northwind.com, phone +91 98765 43210. Hi Priya, Regards, Amit Shah"
    out = redact(text)
    assert "priya.nair" not in out and "98765" not in out
    assert "Priya" not in out and "Amit" not in out
    assert "[email]" in out and "[phone]" in out and "Hi [name]" in out


def test_redacting_filter_formats_args():
    record = logging.LogRecord("mailpilot", logging.INFO, "", 0, "sender %s", ("a@b.com",), None)
    RedactingFilter().filter(record)
    assert record.getMessage() == "sender [email]"


def test_links_from_the_incoming_mail_are_not_repeated():
    mail_text = "Please confirm at https://evil.example/login or write to verify@evil.example. Meeting Friday."
    notes = "My portfolio: https://sam.dev"
    result = check_draft("Friday works. See https://sam.dev and https://evil.example/login, "
                         "or mail verify@evil.example", mail_text + notes, link_source=notes)
    assert "Friday works" in result.text and "https://sam.dev" in result.text
    assert "[confirm: https://evil.example/login]" in result.text
    assert "[confirm: verify@evil.example]" in result.text
