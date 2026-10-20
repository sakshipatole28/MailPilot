import logging

from fastapi import APIRouter, Depends, HTTPException

from app import db
from app.api.mail import get_mail_or_404
from app.api.settings import runtime_settings
from app.config import settings
from app.deps import get_retriever, llm_options
from app.llm.classifier import llm_classify
from app.llm.client import LLMError
from app.llm.generator import draft_reply
from app.models import DraftRequest, Feedback, GeneratedEmail, LLMOptions

log = logging.getLogger("mailpilot.draft")
router = APIRouter(tags=["draft"])


@router.post("/draft", response_model=GeneratedEmail)
def draft(req: DraftRequest, opts: LLMOptions = Depends(llm_options)):
    """classify -> retrieve (filtered by category + sender) -> generate -> guardrails."""
    mail = get_mail_or_404(req.mail_id)
    current = runtime_settings()

    if mail.classified_by != "llm":
        try:
            result = llm_classify(mail, opts, current.categories)
            db.save_classification(mail.id, result)
            mail.category = result.category
        except LLMError as e:
            log.warning("classification failed, keeping keyword label: %s", e)

    chunks, style = [], []
    if req.use_rag:
        retriever = get_retriever()
        query = f"{mail.subject}\n{mail.body[:1000]}"
        chunks = retriever.search(query, k=settings.top_k, category=mail.category,
                                  contact=mail.sender)
        style = retriever.search(query, k=2, contact=mail.sender, doc_type="reply")

    email = draft_reply(mail, chunks, style, req.tone or current.tone, current.user_name,
                        req.instruction, opts)
    email.draft_id = db.save_draft(mail.id, req.instruction, email)
    log.info("draft %s for mail %s: %d sources, %d issues",
             email.draft_id, mail.id, len(chunks), len(email.issues))
    return email


@router.post("/drafts/{draft_id}/feedback")
def feedback(draft_id: int, fb: Feedback):
    if not db.save_feedback(draft_id, fb):
        raise HTTPException(404, "Draft not found")
    return {"ok": True}
