"""(Re)build the vector index from data/context/."""
import logging
from pathlib import Path

from app.rag.chunker import chunk_file
from app.rag.store import VectorStore

log = logging.getLogger("mailpilot.rag")
EXTENSIONS = {".md", ".txt"}


def ingest_dir(context_dir: Path, store: VectorStore) -> dict:
    files = sorted(p for p in Path(context_dir).rglob("*") if p.suffix in EXTENSIONS)
    chunks = [c for f in files for c in chunk_file(f, Path(context_dir))]
    store.reset()
    store.add(chunks)
    log.info("Indexed %d chunks from %d files", len(chunks), len(files))
    return {"files": len(files), "chunks": len(chunks)}


if __name__ == "__main__":
    from app.deps import get_store
    from app.config import settings

    print(ingest_dir(settings.context_dir, get_store()))
