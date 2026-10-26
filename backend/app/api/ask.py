"""Ask your inbox: an agent (app/agents/ask_graph.py) searches the indexed mail, re-searches
with a better query if needed, and answers citing only mails it was shown."""
from fastapi import APIRouter, Depends

from app import db
from app.agents.ask_graph import run_ask_graph
from app.api.settings import runtime_settings
from app.deps import get_mail_retriever, llm_options
from app.jobs import index_mails
from app.models import AskAnswer, AskRequest, LLMOptions

router = APIRouter(tags=["ask"])


@router.post("/ask", response_model=AskAnswer)
def ask(req: AskRequest, opts: LLMOptions = Depends(llm_options)):
    retriever = get_mail_retriever()
    if retriever.store.count() == 0:  # first use, or the worker has not indexed anything yet
        index_mails(db.list_mails())
    if retriever.store.count() == 0:
        return AskAnswer(answer="Your inbox is empty. Sync first.", model=opts.model)
    return run_ask_graph(req.question, retriever, runtime_settings().user_name, opts)
