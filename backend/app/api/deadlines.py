from fastapi import APIRouter, Depends, HTTPException

from app import db
from app.api.mail import get_mail_or_404
from app.deps import llm_options
from app.llm.deadlines import extract_deadlines
from app.models import Deadline, DeadlineExtractRequest, DeadlineUpdate, LLMOptions

router = APIRouter(tags=["deadlines"])


@router.post("/deadlines/extract", response_model=list[Deadline])
def extract(req: DeadlineExtractRequest, opts: LLMOptions = Depends(llm_options)):
    mail = get_mail_or_404(req.mail_id)
    db.save_deadlines(extract_deadlines(mail, opts))
    return db.list_deadlines(include_done=True, mail_id=mail.id)


@router.get("/deadlines", response_model=list[Deadline])
def list_deadlines(include_done: bool = False):
    return db.list_deadlines(include_done=include_done)


@router.patch("/deadlines/{deadline_id}")
def update_deadline(deadline_id: int, update: DeadlineUpdate):
    if not db.set_deadline_done(deadline_id, update.done):
        raise HTTPException(404, "Deadline not found")
    return {"id": deadline_id, "done": update.done}
