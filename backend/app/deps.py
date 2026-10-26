"""Shared objects for the API: the vector store, the retriever and per-request LLM options."""
from functools import lru_cache

from fastapi import Header, HTTPException

from app.config import settings
from app.models import LLMOptions
from app.rag.ingest import ingest_dir
from app.rag.retriever import Retriever
from app.rag.store import Embedder, VectorStore


@lru_cache
def get_embedder() -> Embedder:
    return Embedder(settings.embed_model)  # loaded once, shared by both collections


@lru_cache
def get_store() -> VectorStore:
    return VectorStore(settings.chroma_dir, get_embedder())


@lru_cache
def get_mail_retriever() -> Retriever:
    return Retriever(VectorStore(settings.chroma_dir, get_embedder(), name="mails"))


@lru_cache
def get_retriever() -> Retriever:
    store = get_store()
    if store.count() == 0:
        ingest_dir(settings.context_dir, store)
    reranker = None
    if settings.rerank:
        from sentence_transformers import CrossEncoder
        reranker = CrossEncoder(settings.rerank_model, device="cpu")
    return Retriever(store, reranker)


def llm_options(x_model: str | None = Header(default=None),
                x_api_key: str | None = Header(default=None)) -> LLMOptions:
    """Model and key can come per request (popup Settings) or fall back to the saved settings."""
    from app.api.settings import runtime_settings

    current = runtime_settings()
    model = x_model or current.model
    if current.local_only and not model.startswith("ollama/"):
        raise HTTPException(400, "Local-only mode is on. Pick an ollama/... model in Settings.")
    return LLMOptions(model=model, api_key=x_api_key or None)
