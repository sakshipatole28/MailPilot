from fastapi import APIRouter, Depends

from app import db
from app.api.settings import runtime_settings
from app.config import settings
from app.deps import get_retriever, llm_options
from app.llm.generator import compose_email
from app.models import ComposeRequest, GeneratedEmail, LLMOptions

router = APIRouter(tags=["compose"])


@router.post("/compose", response_model=GeneratedEmail)
def compose(req: ComposeRequest, opts: LLMOptions = Depends(llm_options)):
    current = runtime_settings()
    # No recipient is known yet, so only context not tied to a specific contact is allowed.
    chunks = (get_retriever().search(req.instruction, k=settings.top_k, contact="")
              if req.use_rag else [])
    email = compose_email(req.instruction, chunks, req.tone or current.tone,
                          current.user_name, opts)
    email.draft_id = db.save_draft(None, req.instruction, email)
    return email
