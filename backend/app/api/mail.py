from fastapi import APIRouter, Depends, HTTPException

from app import db
from app.api.settings import runtime_settings
from app.deps import llm_options
from app.llm.classifier import keyword_classify, llm_classify
from app.mail_sources import get_mail_source
from app.models import Classification, ClassifyRequest, LLMOptions, Mail, MailUpdate

router = APIRouter(tags=["mail"])


def get_mail_or_404(mail_id: str) -> Mail:
    mail = db.get_mail(mail_id)
    if mail is None:
        raise HTTPException(404, f"Mail {mail_id} not found")
    return mail


@router.post("/mail/sync")
def sync_mail():
    """Load mails from the active source. New mails get an instant keyword label (no LLM call)."""
    try:
        mails = get_mail_source().fetch()
    except (OSError, RuntimeError) as e:
        raise HTTPException(400, f"Could not read mail source: {e}") from e
    new = db.upsert_mails(mails)
    categories = runtime_settings().categories
    for mail in db.list_mails():
        if mail.category is None:
            db.save_classification(mail.id, keyword_classify(mail, categories))
    return {"fetched": len(mails), "new": new}


@router.get("/mail", response_model=list[Mail])
def list_mail(category: str | None = None):
    return db.list_mails(category)


@router.patch("/mail/{mail_id}", response_model=Mail)
def update_mail(mail_id: str, update: MailUpdate):
    get_mail_or_404(mail_id)
    db.update_mail_flags(mail_id, update.is_read, update.replied)
    return db.get_mail(mail_id)


@router.post("/classify", response_model=Classification)
def classify(req: ClassifyRequest, opts: LLMOptions = Depends(llm_options)):
    mail = get_mail_or_404(req.mail_id)
    result = llm_classify(mail, opts, runtime_settings().categories)
    db.save_classification(mail.id, result)
    return result
