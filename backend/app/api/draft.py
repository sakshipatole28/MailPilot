import logging

from fastapi import APIRouter, Depends, HTTPException

from app import db
from app.api.mail import get_mail_or_404
from app.api.settings import runtime_settings
from app.config import settings
from app.deps import get_retriever, llm_options
from app.jobs import run_triage
from app.llm import security
from app.agents.draft_graph import run_draft_graph
from app.models import DraftRequest, Feedback, GeneratedEmail, LLMOptions

log = logging.getLogger("mailpilot.draft")
router = APIRouter(tags=["draft"])


@router.post("/draft", response_model=GeneratedEmail)
def draft(req: DraftRequest, opts: LLMOptions = Depends(llm_options)):
    """triage (if not done) -> retrieve notes (filtered by category + sender) -> self-correcting
    draft graph (generate -> check -> revise) -> guardrails."""
    mail = get_mail_or_404(req.mail_id)
    current = runtime_settings()

    if mail.triage_status != "done":
        done, _ = run_triage([mail.id], opts)  # failure is fine: draft with the keyword label
        mail = done[0] if done else mail

    # Defense in depth: mail that may be steering the AI (regex detector or triage's LLM judge)
    # never gets the user's notes or quick replies, so an injection has nothing private to leak
    # and no one-tap commitment to plant.
    unsafe = security.unsafe_for_drafting(mail)
    chunks, style = [], []
    if req.use_rag and not unsafe:
        retriever = get_retriever()
        query = f"{mail.subject}\n{mail.body[:1000]}"
        chunks = retriever.search(query, k=settings.top_k, category=mail.category,
                                  contact=mail.sender)
        style = retriever.search(query, k=2, contact=mail.sender, doc_type="reply")

    email = run_draft_graph(mail, chunks, style, req.tone or current.tone, current.user_name,
                            req.instruction, opts)
    if unsafe:
        email.quick_replies = []
        email.issues.insert(0, "This mail may be trying to manipulate the assistant or is suspicious: "
                               "your notes were not used. Check every sentence before sending.")
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
