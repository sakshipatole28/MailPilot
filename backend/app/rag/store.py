"""Local embeddings (sentence-transformers) + persistent Chroma collection."""
import chromadb
from chromadb.config import Settings as ChromaSettings

from app.rag.chunker import Chunk

# bge v1.5 recommends this prefix on queries (not on documents) for retrieval.
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:  # lazy: the model takes a few seconds to load
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name, device="cpu")
        return self._model

    def embed_docs(self, texts: list[str]) -> list[list[float]]:
        return self._load().encode(texts, normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> list[float]:
        prefix = BGE_QUERY_PREFIX if "bge" in self.model_name else ""
        return self._load().encode(prefix + text, normalize_embeddings=True).tolist()


class VectorStore:
    COLLECTION = "context"

    def __init__(self, path, embedder):
        self.embedder = embedder
        self.client = chromadb.PersistentClient(
            path=str(path), settings=ChromaSettings(anonymized_telemetry=False)
        )
        self.collection = self._open()
        self.version = 0  # bumped on every write so the BM25 index knows to rebuild

    def _open(self):
        return self.client.get_or_create_collection(
            self.COLLECTION, metadata={"hnsw:space": "cosine"}, embedding_function=None
        )

    def reset(self) -> None:
        self.client.delete_collection(self.COLLECTION)
        self.collection = self._open()
        self.version += 1

    def add(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        self.collection.add(
            ids=[c.id for c in chunks],
            documents=[c.text for c in chunks],
            metadatas=[c.meta for c in chunks],
            embeddings=self.embedder.embed_docs([c.text for c in chunks]),
        )
        self.version += 1

    def count(self) -> int:
        return self.collection.count()

    def query(self, text: str, n: int, where: dict | None = None) -> list[str]:
        """Chunk ids, most similar first."""
        if self.count() == 0:
            return []
        result = self.collection.query(
            query_embeddings=[self.embedder.embed_query(text)],
            n_results=min(n, self.count()),
            where=where or None,
        )
        return result["ids"][0]

    def all_chunks(self) -> list[Chunk]:
        data = self.collection.get(include=["documents", "metadatas"])
        return [Chunk(id=i, text=d, meta=m)
                for i, d, m in zip(data["ids"], data["documents"], data["metadatas"])]
