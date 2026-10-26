"""Ask your inbox: hybrid search over indexed mail, then an answer that cites the mails it used."""
from fastapi import APIRouter, Depends

from app import db
from app.api.settings import runtime_settings
from app.config import settings
from app.deps import get_mail_retriever, llm_options
from app.jobs import index_mails
from app.llm import security
from app.llm.client import complete_json, render_prompt
from app.models import AskAnswer, AskRequest, Citation, LLMOptions

router = APIRouter(tags=["ask"])


@router.post("/ask", response_model=AskAnswer)
def ask(req: AskRequest, opts: LLMOptions = Depends(llm_options)):
    retriever = get_mail_retriever()
    if retriever.store.count() == 0:  # first use, or the worker has not indexed anything yet
        index_mails(db.list_mails())
    hits = retriever.search(req.question, k=6)
    mails = db.get_mails([h.source for h in hits])
    if not mails:
        return AskAnswer(answer="Your inbox has no mail that matches this question.", model=opts.model)

    blocks = "\n\n".join(
        f"[id: {m.id}] From: {m.sender_name} <{m.sender}> | Date: {m.received_at:%a %d %b %Y %H:%M}"
        f" | Subject: {m.subject}\n{m.body[:1200]}" for m in mails)
    marked, note = security.spotlight(blocks, settings.spotlight)
    data = complete_json(render_prompt(
        "ask", user_name=runtime_settings().user_name, untrusted_note=note,
        question=req.question, emails=marked), opts)

    by_id = {m.id: m for m in mails}
    cited = [by_id[i] for i in data.get("mail_ids", []) if i in by_id]  # only mails we showed it
    return AskAnswer(
        answer=security.unmark(str(data.get("answer", ""))).strip() or "No answer.",
        citations=[Citation(mail_id=m.id, subject=m.subject, sender=m.sender,
                            received_at=m.received_at) for m in cited],
        model=opts.model,
    )
