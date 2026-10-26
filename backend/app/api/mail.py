from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from app import db
from app.api.settings import runtime_settings
from app.deps import llm_options
from app.jobs import run_triage, worker
from app.llm.classifier import keyword_classify
from app.mail_sources import get_mail_source
from app.models import (Brief, Classification, ClassifyRequest, LLMOptions, Mail, MailUpdate,
                        TriageRequest)

router = APIRouter(tags=["mail"])


def get_mail_or_404(mail_id: str) -> Mail:
    mail = db.get_mail(mail_id)
    if mail is None:
        raise HTTPException(404, f"Mail {mail_id} not found")
    return mail


@router.post("/mail/sync")
def sync_mail():
    """Load mail from the active source. New mail gets an instant keyword label, then is queued
    for background triage (one LLM call each) and indexed for search."""
    try:
        mails = get_mail_source().fetch()
    except Exception as e:  # missing file, expired Gmail login, Gmail rate limit, offline ...
        raise HTTPException(503, f"Could not read mail source: {str(e)[:300]}") from e
    new = db.upsert_mails(mails)
    names = [c.name for c in runtime_settings().categories]
    for mail in db.list_mails():
        if mail.category is None:
            db.save_classification(mail.id, keyword_classify(mail, names))
    queued = worker.enqueue(db.untriaged_mail_ids())
    return {"fetched": len(mails), "new": new, "queued": queued}


@router.get("/mail", response_model=list[Mail])
def list_mail(category: str | None = None):
    return db.list_mails(category)


@router.patch("/mail/{mail_id}", response_model=Mail)
def update_mail(mail_id: str, update: MailUpdate):
    get_mail_or_404(mail_id)
    db.update_mail_flags(mail_id, update.is_read, update.replied)
    if update.category is not None:
        names = [c.name for c in runtime_settings().categories]
        if update.category not in names:
            raise HTTPException(422, f"Unknown category {update.category!r}")
        db.set_user_category(mail_id, update.category)  # remembered as a few-shot example
    return db.get_mail(mail_id)


@router.post("/classify", response_model=Classification)
def classify(req: ClassifyRequest, opts: LLMOptions = Depends(llm_options)):
    """Triage one mail now (category is part of triage) and return its classification."""
    get_mail_or_404(req.mail_id)
    done, failed = run_triage([req.mail_id], opts)
    if failed:
        raise HTTPException(502, "Triage failed; see the backend log")
    mail = done[0]
    return Classification(category=mail.category, priority=mail.priority or "low",
                          needs_reply=bool(mail.needs_reply), reason=mail.summary,
                          method=mail.classified_by or "llm")


@router.post("/triage")
def triage(req: TriageRequest, opts: LLMOptions = Depends(llm_options)):
    """Triage now with this request's model/key (the popup's "Triage now"), up to `limit` mails."""
    ids = (req.mail_ids or db.untriaged_mail_ids())[:req.limit]
    done, failed = run_triage(ids, opts)
    return {"triaged": len(done), "failed": failed, "remaining": len(db.untriaged_mail_ids())}


@router.get("/triage/status")
def triage_status():
    counts = db.triage_counts()
    return {"queued": worker.pending(), "done": counts.get("done", 0),
            "pending": counts.get("pending", 0), "failed": counts.get("failed", 0),
            "new": counts.get("new", 0)}


@router.get("/brief", response_model=Brief)
def brief():
    """What needs attention today. Pure aggregation over triage results: no LLM call."""
    mails = db.list_mails()
    now = datetime.now(timezone.utc)
    soon = now + timedelta(days=3)
    tasks = [t for t in db.list_deadlines()
             if t.due_iso and datetime.fromisoformat(t.due_iso) <= soon]
    by_score = lambda m: m.priority_score if m.priority_score is not None else -1  # noqa: E731
    return Brief(
        needs_reply=sorted([m for m in mails if m.needs_reply and not m.replied
                            and m.risk_level != "high"], key=by_score, reverse=True)[:5],
        due_soon=tasks[:8],
        suspicious=[m for m in mails if m.risk_level == "high"][:5],
        unread=sum(not m.is_read for m in mails),
        pending_triage=sum(m.triage_status in (None, "pending") for m in mails),
    )
