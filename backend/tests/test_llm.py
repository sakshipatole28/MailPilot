from datetime import datetime

import litellm
import pytest

from app.config import DEFAULT_CATEGORIES
from app.llm import client
from app.llm.classifier import keyword_classify, llm_classify
from app.llm.client import LLMError, complete, parse_json
from app.llm.deadlines import evidence_found, extract_deadlines
from app.llm.generator import compose_email, draft_reply
from app.models import LLMOptions, Mail, SourceChunk
from tests.conftest import as_json

OPTS = LLMOptions(model="groq/test-model")


def make_mail(subject="Interview schedule", body="Please reply by tomorrow EOD.",
              sender="priya@northwind.com"):
    return Mail(id="m1", sender=sender, sender_name="Priya Nair", subject=subject, body=body,
                received_at=datetime.fromisoformat("2026-10-20T14:30:00+05:30"))


# ---- client ----

def test_parse_json_handles_fences_and_chatter():
    assert parse_json('Sure!\n```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(LLMError):
        parse_json("no json here")


def test_complete_caches_responses(fake_llm):
    fake_llm.reply = "hello"
    assert complete("hi", OPTS) == "hello"
    assert complete("hi", OPTS) == "hello"
    assert len(fake_llm.calls) == 1  # second call served from the cache
    complete("hi", LLMOptions(model="other/model"))
    assert len(fake_llm.calls) == 2  # different model -> different cache key


def test_complete_retries_rate_limits(monkeypatch, fake_llm):
    monkeypatch.setattr(client.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise litellm.exceptions.RateLimitError("slow down", "groq", "test-model")
        return fake_llm(**kwargs)

    monkeypatch.setattr(litellm, "completion", flaky)
    fake_llm.reply = "ok"
    assert complete("retry me", OPTS) == "ok"
    assert calls["n"] == 2


def test_complete_retries_empty_replies(fake_llm):
    replies = iter(["", "ok"])
    fake_llm.reply = lambda prompt: next(replies)
    assert complete("empty first", OPTS) == "ok"
    assert len(fake_llm.calls) == 2


def test_parse_json_allows_raw_newlines_in_strings():
    assert parse_json('{"body": "line one\nline two"}') == {"body": "line one\nline two"}


def test_complete_json_asks_again_after_bad_json(fake_llm):
    from app.llm.client import complete_json
    fake_llm.reply = lambda prompt: '{"a": 1}' if "not valid JSON" in prompt else '{"a": oops}'
    assert complete_json("give json", OPTS) == {"a": 1}


def test_complete_does_not_retry_auth_errors(monkeypatch):
    calls = {"n": 0}

    def bad_key(**kwargs):
        calls["n"] += 1
        raise litellm.exceptions.AuthenticationError("bad key", "groq", "test-model")

    monkeypatch.setattr(litellm, "completion", bad_key)
    with pytest.raises(LLMError):
        complete("x", OPTS)
    assert calls["n"] == 1


def test_user_key_is_passed_per_request(fake_llm):
    complete("x", LLMOptions(model="gpt-4o-mini", api_key="sk-user"))
    assert fake_llm.calls[0]["api_key"] == "sk-user"


# ---- classifier ----

def test_keyword_classifier():
    mail = make_mail(subject="DBMS assignment 3", body="Submit the assignment on Moodle.",
                     sender="prof@westbrook.edu")
    assert keyword_classify(mail, DEFAULT_CATEGORIES).category == "Academic"
    newsletter = make_mail(subject="Weekly digest", body="Top stories. Unsubscribe")
    result = keyword_classify(newsletter, DEFAULT_CATEGORIES)
    assert result.category == "Other" and result.needs_reply is False
    general = ["Education", "Newsletters", "Promotions", "Other"]
    assert keyword_classify(newsletter, general).category == "Newsletters"
    promo = make_mail(subject="Hello", body="hi")
    promo.labels = ["CATEGORY_PROMOTIONS"]
    assert keyword_classify(promo, general).category == "Promotions"  # Gmail tab wins


def test_llm_classifier_validates_output(fake_llm):
    fake_llm.reply = as_json({"category": "hr/recruiter", "priority": "URGENT", "needs_reply": True})
    result = llm_classify(make_mail(), OPTS, DEFAULT_CATEGORIES)
    assert result.category == "HR/Recruiter"  # case-insensitive match to a known category
    assert result.priority == "medium"        # unknown priority falls back
    assert result.method == "llm"

    fake_llm.reply = as_json({"category": "Spam", "priority": "low", "needs_reply": False})
    assert llm_classify(make_mail(subject="x"), OPTS, DEFAULT_CATEGORIES).category == "Other"


# ---- deadlines ----

def test_deadlines_keep_only_supported_items(fake_llm):
    fake_llm.reply = as_json({"deadlines": [
        {"title": "Reply with slot", "due_iso": "2026-10-21T23:59:00+05:30",
         "evidence": "reply by tomorrow EOD", "confidence": 0.9},
        {"title": "Invented", "due_iso": "2026-10-30T10:00:00+05:30",
         "evidence": "the offsite on the 30th", "confidence": 0.8},    # not in the mail
        {"title": "Bad date", "due_iso": "next week", "evidence": "tomorrow EOD"},
        {"title": "Too early", "due_iso": "2025-01-01T10:00:00+05:30", "evidence": "tomorrow EOD"},
    ]})
    items = extract_deadlines(make_mail(), OPTS)
    assert [d.title for d in items] == ["Reply with slot"]
    assert items[0].due_iso.startswith("2026-10-21")


def test_relative_dates_get_received_date_in_prompt(fake_llm):
    fake_llm.reply = '{"deadlines": []}'
    extract_deadlines(make_mail(), OPTS)
    prompt = fake_llm.calls[0]["messages"][0]["content"]
    assert "2026-10-20T14:30:00+05:30 (Tuesday)" in prompt
    assert "Tue 20 Oct 2026 (received)" in prompt and "Sun 25 Oct 2026" in prompt


def test_same_date_items_are_merged(fake_llm):
    fake_llm.reply = as_json({"deadlines": [
        {"title": "Submit report", "due_iso": "2026-10-30T23:59:00+05:30", "evidence": "tomorrow EOD"},
        {"title": "Prepare demo", "due_iso": "2026-10-30T23:59:00+05:30", "evidence": "tomorrow EOD"},
    ]})
    assert [d.title for d in extract_deadlines(make_mail(), OPTS)] == ["Submit report"]


def test_evidence_matching_tolerates_small_rewording():
    assert evidence_found("by 23 October 2026, 5:00 PM", "Register by 23 October 2026, 5:00 PM.")
    assert not evidence_found("on 30 November", "Register by 23 October 2026.")


# ---- generator ----

def test_draft_reply_runs_guardrails(fake_llm):
    fake_llm.reply = as_json({"subject": "Re: Interview schedule",
                              "body": "Hi Priya,\n\nThursday works. See https://evil.example "
                                      "and call me on Monday.\n\nSam"})
    chunk = SourceChunk(id="c1", text="Available Thursday afternoons.", source="notes/a.md")
    result = draft_reply(make_mail(), [chunk], [], "friendly", "Sam", "", OPTS)
    assert "[confirm: https://evil.example]" in result.body
    assert "[confirm: Monday]" in result.body
    assert "Thursday works" in result.body  # supported by the context chunk
    assert len(result.issues) == 2
    assert result.sources == [chunk]


def test_draft_falls_back_to_raw_text(fake_llm):
    fake_llm.reply = "Hi Priya, thanks! Sam"
    result = draft_reply(make_mail(), [], [], "friendly", "Sam", "", OPTS)
    assert result.subject == "Re: Interview schedule"
    assert result.body == "Hi Priya, thanks! Sam"


def test_compose_uses_instruction_as_source(fake_llm):
    fake_llm.reply = as_json({"subject": "Rescheduling my interview",
                              "body": "Dear HR,\n\nCould we move my interview from Friday to "
                                      "a later date? [preferred date]\n\nSam"})
    result = compose_email("ask HR to reschedule my Friday interview", [], "polite", "Sam", OPTS)
    assert result.issues == []
    assert "[preferred date]" in result.body
