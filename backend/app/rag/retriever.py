"""Hybrid retrieval: vector (Chroma) + keyword (BM25), merged with reciprocal rank fusion."""
import re

from rank_bm25 import BM25Okapi

from app.models import SourceChunk
from app.rag.chunker import Chunk
from app.rag.store import VectorStore

STOPWORDS = set("a an and are as at be by for from has have i in is it of on or our the this to "
                "we with you your my me will can".split())


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


def rrf(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    """Reciprocal rank fusion: score(d) = sum over rankings of 1 / (k + rank)."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


def build_where(category: str | None, contact: str | None, doc_type: str | None) -> dict | None:
    conditions = []
    if category:
        conditions.append({"category": {"$in": [category, "any"]}})
    if contact is not None:
        conditions.append({"contact": {"$in": [contact.lower(), ""]}})
    if doc_type:
        conditions.append({"doc_type": doc_type})
    if not conditions:
        return None
    return conditions[0] if len(conditions) == 1 else {"$and": conditions}


def matches(meta: dict, category: str | None, contact: str | None, doc_type: str | None) -> bool:
    """The same filter as build_where, for the BM25 side."""
    if category and meta.get("category") not in (category, "any"):
        return False
    if contact is not None and meta.get("contact", "") not in (contact.lower(), ""):
        return False
    return not doc_type or meta.get("doc_type") == doc_type


class Retriever:
    def __init__(self, store: VectorStore, reranker=None):
        self.store = store
        self.reranker = reranker  # optional sentence_transformers.CrossEncoder
        self._bm25 = None
        self._chunks: list[Chunk] = []
        self._bm25_version = -1

    def _bm25_index(self):
        if self._bm25_version != self.store.version or self._bm25 is None:
            self._chunks = self.store.all_chunks()
            self._bm25 = BM25Okapi([tokenize(c.text) for c in self._chunks]) if self._chunks else None
            self._bm25_version = self.store.version
        return self._bm25

    def _bm25_ranking(self, query: str, n: int, category, contact, doc_type) -> list[str]:
        index = self._bm25_index()
        if index is None:
            return []
        scores = index.get_scores(tokenize(query))
        ranked = sorted(range(len(self._chunks)), key=lambda i: scores[i], reverse=True)
        return [self._chunks[i].id for i in ranked
                if scores[i] > 0 and matches(self._chunks[i].meta, category, contact, doc_type)][:n]

    def search(self, query: str, k: int = 4, category: str | None = None,
               contact: str | None = None, doc_type: str | None = None,
               mode: str = "hybrid") -> list[SourceChunk]:
        """mode: "hybrid" (default), "vector" or "bm25" (the last two exist for the eval)."""
        n = max(k * 5, 20)
        rankings = []
        if mode in ("hybrid", "vector"):
            rankings.append(self.store.query(query, n, build_where(category, contact, doc_type)))
        if mode in ("hybrid", "bm25"):
            rankings.append(self._bm25_ranking(query, n, category, contact, doc_type))
        fused = rrf(rankings)

        self._bm25_index()  # make sure self._chunks is loaded for the lookup below
        by_id = {c.id: c for c in self._chunks}
        candidates = [(by_id[i], s) for i, s in fused if i in by_id]

        if self.reranker is not None and candidates:
            pool = candidates[: k * 3]
            scores = self.reranker.predict([(query, c.text) for c, _ in pool])
            candidates = sorted(zip([c for c, _ in pool], scores), key=lambda x: x[1], reverse=True)

        return [SourceChunk(id=c.id, text=c.text, source=c.meta.get("source", ""),
                            title=c.meta.get("title", ""), score=round(float(s), 4))
                for c, s in candidates[:k]]
