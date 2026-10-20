from fastapi import APIRouter

from app.config import settings
from app.deps import get_store
from app.rag.ingest import ingest_dir

router = APIRouter(tags=["rag"])


@router.post("/rag/ingest")
def ingest():
    """Re-index data/context/ (run after you edit your resume, notes or past replies)."""
    return ingest_dir(settings.context_dir, get_store())
