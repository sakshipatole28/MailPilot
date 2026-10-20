"""Test fixtures: a temp database, a fake LLM and a fake embedder (no network, no model download)."""
import hashlib
import json
import re

import litellm
import pytest

from app import db
from app.config import settings


class FakeEmbedder:
    """Hashed bag-of-words vectors: similar wording -> similar vectors, deterministic and instant."""
    model_name = "fake"
    dim = 256

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for tok in re.findall(r"[a-z0-9]+", text.lower()):
            v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dim] += 1.0
        norm = sum(x * x for x in v) ** 0.5 or 1.0
        return [x / norm for x in v]

    def embed_docs(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


class FakeLLM:
    """Replaces litellm.completion. Set .reply (str or callable(prompt) -> str)."""

    def __init__(self):
        self.reply = "{}"
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        prompt = kwargs["messages"][-1]["content"]
        text = self.reply(prompt) if callable(self.reply) else self.reply
        message = type("Msg", (), {"content": text})
        choice = type("Choice", (), {"message": message})
        return type("Resp", (), {"choices": [choice]})


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "test.db")
    monkeypatch.setattr(settings, "chroma_dir", tmp_path / "chroma")
    monkeypatch.setattr(settings, "llm_retries", 1)
    db.init_db()
    yield


@pytest.fixture
def fake_llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(litellm, "completion", fake)
    return fake


@pytest.fixture
def fake_embedder():
    return FakeEmbedder()


def as_json(obj) -> str:
    return json.dumps(obj)
