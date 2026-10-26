from datetime import datetime

import litellm
import pytest

from app import db
from app.agents.ask_graph import MAX_SEARCHES, run_ask_graph
from app.agents.draft_graph import MAX_REVISIONS, run_draft_graph
from app.llm import client
from app.models import LLMOptions, Mail, SourceChunk
from app.rag.retriever import Retriever
from app.rag.store import VectorStore
from app.jobs import mail_chunk
from tests.conftest import as_json

OPTS = LLMOptions(model="groq/test-model")
MAIL = Mail(id="m1", sender="priya@northwind.com", sender_name="Priya Nair",
            subject="Interview schedule", body="Can you do Thursday 22 October at 11:00 AM?",
            received_at=datetime.fromisoformat("2026-10-20T14:30:00+05:30"))
NOTES = [SourceChunk(id="c1", text="Available weekdays after 2 PM.", source="notes/a.md")]


def is_revision(prompt: str) -> bool:
    return "DRAFT TO REVISE" in prompt


# ---- draft graph ----

def test_draft_graph_revises_unsupported_facts(fake_llm):
    fake_llm.reply = lambda p: as_json(
        {"subject": "Re: Interview", "body": "Hi Priya, Thursday 22 October at 11:00 AM works. [confirm time]\nSam"}
        if is_revision(p) else
        {"subject": "Re: Interview", "body": "Hi Priya, Thursday 22 October at 11:00 AM works, or "
                                             "Monday at 4 PM.\nSam", "quick_replies": []})
    result = run_draft_graph(MAIL, NOTES, [], "friendly", "Sam", "", OPTS)
    assert result.first_pass_issues == 2 and result.revisions == 1
    assert result.issues == [] and "Monday" not in result.body
    revise_prompt = [c["messages"][0]["content"] for c in fake_llm.calls if is_revision(c["messages"][0]["content"])][0]
    assert "Unsupported weekday 'Monday'" in revise_prompt and "<MAIL-" in revise_prompt


def test_draft_graph_stops_after_max_revisions_and_masks_the_rest(fake_llm):
    fake_llm.reply = as_json({"subject": "Re", "body": "See you Monday.", "quick_replies": []})
    result = run_draft_graph(MAIL, NOTES, [], "friendly", "Sam", "", OPTS)
    assert result.revisions == MAX_REVISIONS
    assert "[confirm: Monday]" in result.body and result.issues
    assert len(fake_llm.calls) == 2  # the 2nd identical revision request is served from cache


def test_clean_draft_needs_no_revision(fake_llm):
    fake_llm.reply = as_json({"subject": "Re", "body": "Thursday works for me. Sam", "quick_replies": []})
    result = run_draft_graph(MAIL, NOTES, [], "friendly", "Sam", "", OPTS)
    assert result.revisions == 0 and result.first_pass_issues == 0 and len(fake_llm.calls) == 1


# ---- ask graph ----

@pytest.fixture
def inbox(tmp_path, fake_embedder):
    mails = [
        Mail(id="a", sender="hr@contoso.com", sender_name="Contoso HR", subject="Technical round",
             body="Your technical round is on Monday 26 October at 10:30 AM.",
             received_at="2026-10-20T10:00:00+05:30"),
        Mail(id="b", sender="news@x.io", subject="Weekly digest", body="Top stories this week.",
             received_at="2026-10-19T10:00:00+05:30"),
    ]
    db.upsert_mails(mails)
    store = VectorStore(tmp_path / "chroma", fake_embedder, name="mails")
    store.upsert([mail_chunk(m) for m in mails])
    return Retriever(store)


def test_ask_agent_searches_again_then_answers(fake_llm, inbox):
    steps = iter([
        {"action": "search", "query": "Contoso technical round", "answer": "", "mail_ids": []},
        {"action": "answer", "query": "", "answer": "Monday 26 October at 10:30 AM.",
         "mail_ids": ["a", "made-up"]},
    ])
    fake_llm.reply = lambda p: as_json(next(steps))
    result = run_ask_graph("when is my interview?", inbox, "Sam", OPTS)
    assert result.searches == ["when is my interview?", "Contoso technical round"]
    assert result.answer.startswith("Monday") and [c.mail_id for c in result.citations] == ["a"]


def test_ask_agent_must_answer_after_max_searches(fake_llm, inbox):
    counter = iter(range(100))
    fake_llm.reply = lambda p: as_json({"action": "search", "query": f"query {next(counter)}",
                                        "answer": "", "mail_ids": []})
    result = run_ask_graph("anything?", inbox, "Sam", OPTS)
    assert len(result.searches) == MAX_SEARCHES
    assert "could not find" in result.answer
    assert "last step, so you must answer now" in fake_llm.calls[-1]["messages"][0]["content"]


# ---- structured outputs ----

def test_schema_is_sent_when_supported(fake_llm, monkeypatch):
    monkeypatch.setattr(client, "supports_schema", lambda model: True)
    fake_llm.reply = '{"a": 1}'
    client.complete("x", OPTS, schema={"type": "object"}, name="thing")
    rf = fake_llm.calls[0]["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["name"] == "thing"
    assert rf["json_schema"]["strict"] is True


def test_schema_rejection_falls_back_to_prompt_only(fake_llm, monkeypatch):
    monkeypatch.setattr(litellm, "supports_response_schema", lambda model: True)
    client._NO_SCHEMA.discard(OPTS.model)
    calls = []

    def picky(**kwargs):
        calls.append(kwargs)
        if "response_format" in kwargs:
            raise litellm.exceptions.BadRequestError("response_format not supported", OPTS.model, "groq")
        return fake_llm(**kwargs)

    monkeypatch.setattr(litellm, "completion", picky)
    fake_llm.reply = '{"ok": true}'
    assert client.complete_json("y", OPTS, schema={"type": "object"}) == {"ok": True}
    assert "response_format" not in calls[-1] and OPTS.model in client._NO_SCHEMA
    client._NO_SCHEMA.discard(OPTS.model)


# ---- tracing ----

def test_spans_are_recorded_without_mail_text(fake_llm):
    from app.tracing import setup_tracing

    setup_tracing()
    fake_llm.reply = as_json({"subject": "Re", "body": "Thursday works. Sam", "quick_replies": []})
    run_draft_graph(MAIL, NOTES, [], "friendly", "Sam", "", OPTS)
    names = [s["name"] for t in db.recent_traces(5) for s in t["spans"]]
    assert {"graph.draft", "graph.draft.generate", "llm.complete"} <= set(names)
    stored = str(db.recent_traces(5))
    assert "Thursday" not in stored and "Priya" not in stored  # no mail or draft text in traces
