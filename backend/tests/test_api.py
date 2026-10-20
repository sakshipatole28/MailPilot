import pytest
from fastapi.testclient import TestClient

from app import deps
from app.config import ROOT
from app.main import app
from app.rag.ingest import ingest_dir
from app.rag.retriever import Retriever
from app.rag.store import VectorStore
from tests.conftest import as_json


@pytest.fixture
def api(tmp_path, fake_embedder, fake_llm, monkeypatch):
    store = VectorStore(tmp_path / "chroma", fake_embedder)
    ingest_dir(ROOT / "data" / "context", store)
    monkeypatch.setattr(deps, "get_store", lambda: store)
    retriever = Retriever(store)
    for module in ("app.api.draft", "app.api.compose"):
        monkeypatch.setattr(f"{module}.get_retriever", lambda: retriever)
    monkeypatch.setattr("app.api.rag.get_store", lambda: store)
    client = TestClient(app)
    assert client.post("/mail/sync").json()["new"] >= 50
    return client


def test_sync_assigns_keyword_labels(api):
    mails = api.get("/mail").json()
    assert all(m["category"] and m["classified_by"] == "keywords" for m in mails)
    assert api.post("/mail/sync").json()["new"] == 0  # idempotent


def test_classify_endpoint(api, fake_llm):
    fake_llm.reply = as_json({"category": "HR/Recruiter", "priority": "high", "needs_reply": True})
    r = api.post("/classify", json={"mail_id": "m012"}, headers={"X-Model": "groq/x"})
    assert r.status_code == 200 and r.json()["category"] == "HR/Recruiter"
    assert fake_llm.calls[-1]["model"] == "groq/x"
    mail = [m for m in api.get("/mail").json() if m["id"] == "m012"][0]
    assert mail["classified_by"] == "llm"


def test_llm_failure_returns_502(api, monkeypatch):
    import litellm

    def boom(**kwargs):
        raise litellm.exceptions.AuthenticationError("no key", "gemini", "x")

    monkeypatch.setattr(litellm, "completion", boom)
    r = api.post("/classify", json={"mail_id": "m001"})
    assert r.status_code == 502


def test_deadline_flow(api, fake_llm):
    fake_llm.reply = as_json({"deadlines": [
        {"title": "Reply with slot", "due_iso": "2026-10-21T23:59:00+05:30",
         "evidence": "by tomorrow EOD", "confidence": 0.9}]})
    r = api.post("/deadlines/extract", json={"mail_id": "m012"})
    assert r.status_code == 200 and len(r.json()) == 1
    api.post("/deadlines/extract", json={"mail_id": "m012"})  # no duplicates on re-run
    items = api.get("/deadlines").json()
    assert len(items) == 1 and items[0]["mail_subject"] == "Interview schedule - Software Engineer"
    api.patch(f"/deadlines/{items[0]['id']}", json={"done": True})
    assert api.get("/deadlines").json() == []
    assert len(api.get("/deadlines?include_done=true").json()) == 1


def test_draft_and_feedback(api, fake_llm):
    def reply(prompt):
        if "Return only JSON, no other text:\n{\"category\"" in prompt:
            return as_json({"category": "HR/Recruiter", "priority": "high", "needs_reply": True})
        return as_json({"subject": "Re: Interview", "body": "Hi Priya,\n\nThursday 22 October at "
                        "11:00 AM works for me.\n\nBest,\nSam Rivera"})

    fake_llm.reply = reply
    r = api.post("/draft", json={"mail_id": "m012"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["issues"] == [] and body["sources"] and body["draft_id"]
    assert api.post(f"/drafts/{body['draft_id']}/feedback", json={"rating": 4}).json() == {"ok": True}
    assert api.post("/drafts/999/feedback", json={"rating": 4}).status_code == 404

    no_rag = api.post("/draft", json={"mail_id": "m012", "use_rag": False}).json()
    assert no_rag["sources"] == []


def test_compose(api, fake_llm):
    fake_llm.reply = as_json({"subject": "Reschedule", "body": "Dear [recipient name], ... Sam"})
    r = api.post("/compose", json={"instruction": "ask HR to reschedule my interview"})
    assert r.status_code == 200 and r.json()["subject"] == "Reschedule"


def test_settings_and_local_only(api):
    s = api.post("/settings", json={"tone": "formal", "local_only": True}).json()
    assert s["tone"] == "formal" and s["local_only"] is True
    r = api.post("/classify", json={"mail_id": "m001"}, headers={"X-Model": "gpt-4o-mini"})
    assert r.status_code == 400  # local-only blocks cloud models


def test_mark_replied_and_404(api):
    assert api.patch("/mail/m012", json={"replied": True}).json()["replied"] is True
    assert api.patch("/mail/nope", json={"replied": True}).status_code == 404


def test_rag_ingest_endpoint(api):
    assert api.post("/rag/ingest").json()["chunks"] > 0
