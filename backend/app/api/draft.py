import logging

from fastapi import APIRouter, Depends, HTTPException

from app import db
from app.api.mail import get_mail_or_404
from app.api.settings import runtime_settings
from app.config import settings
from app.deps import get_retriever, llm_options
from app.jobs import run_triage
from app.llm import security
from app.llm.generator import draft_reply
from app.models import DraftRequest, Feedback, GeneratedEmail, LLMOptions

log = logging.getLogger("mailpilot.draft")
router = APIRouter(tags=["draft"])


@router.post("/draft", response_model=GeneratedEmail)
def draft(req: DraftRequest, opts: LLMOptions = Depends(llm_options)):
    """triage (if not done) -> retrieve (filtered by category + sender) -> generate -> guardrails."""
    mail = get_mail_or_404(req.mail_id)
    current = runtime_settings()

    if mail.triage_status != "done":
        done, _ = run_triage([mail.id], opts)  # failure is fine: draft with the keyword label
        mail = done[0] if done else mail

    # Defense in depth: a mail that tries to instruct the AI never gets the user's notes,
    # so a successful injection still has nothing private to leak.
    injected = security.looks_like_injection(f"{mail.subject}\n{mail.body}")
    chunks, style = [], []
    if req.use_rag and not injected:
        retriever = get_retriever()
        query = f"{mail.subject}\n{mail.body[:1000]}"
        chunks = retriever.search(query, k=settings.top_k, category=mail.category,
                                  contact=mail.sender)
        style = retriever.search(query, k=2, contact=mail.sender, doc_type="reply")

    email = draft_reply(mail, chunks, style, req.tone or current.tone, current.user_name,
                        req.instruction, opts)
    if injected:
        email.issues.insert(0, "This mail contains instructions aimed at AI assistants; your notes "
                               "were not used. Check the draft carefully.")
    if mail.risk_level == "high":
        email.issues.insert(0, "This mail looks like phishing: " + "; ".join(mail.risk_reasons[:2]))
    email.draft_id = db.save_draft(mail.id, req.instruction, email)
    log.info("draft %s for mail %s: %d sources, %d issues",
             email.draft_id, mail.id, len(chunks), len(email.issues))
    return email


@router.post("/drafts/{draft_id}/feedback")
def feedback(draft_id: int, fb: Feedback):
    if not db.save_feedback(draft_id, fb):
        raise HTTPException(404, "Draft not found")
    return {"ok": True}
