"""Ask your inbox as a small agent (LangGraph): search, read, decide, search again if needed.

    search -> decide --(needs more)--> search -> decide ... --(enough / out of searches)--> END

The first search uses the question itself, so most questions need one LLM call. When the
first results miss (the user asks "when is my interview?" but the mail says "technical round
scheduled"), the model proposes a different query, a ReAct-style loop (Yao et al., ICLR 2023)
with one tool. Answers may only cite mails the agent was shown.
"""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app import db
from app.config import settings
from app.llm import schemas, security
from app.llm.client import complete_json, render_prompt
from app.models import AskAnswer, Citation, LLMOptions, Mail
from app.rag.retriever import Retriever
from app.tracing import span

MAX_SEARCHES = 3
PER_SEARCH = 5


class AskState(TypedDict, total=False):
    question: str
    user_name: str
    opts: LLMOptions
    retriever: Retriever
    next_query: str
    queries: list[str]
    found: dict[str, Mail]  # insertion-ordered: earlier searches first
    answer: str
    mail_ids: list[str]


def search(state: AskState) -> dict:
    query = state["next_query"]
    hits = state["retriever"].search(query, k=PER_SEARCH)
    found = dict(state.get("found", {}))
    for mail in db.get_mails([h.source for h in hits]):
        found.setdefault(mail.id, mail)
    return {"queries": [*state.get("queries", []), query], "found": found}


def _emails(found: dict[str, Mail]) -> str:
    if not found:
        return "(no emails found)"
    return "\n\n".join(
        f"[id: {m.id}] From: {m.sender_name} <{m.sender}> | Date: {m.received_at:%a %d %b %Y %H:%M}"
        f" | Subject: {m.subject}\n{m.body[:1000]}" for m in list(found.values())[:12])


def decide(state: AskState) -> dict:
    last_chance = len(state["queries"]) >= MAX_SEARCHES
    marked, note = security.spotlight(_emails(state["found"]), settings.spotlight)
    with span("graph.ask.decide", searches=len(state["queries"]), mails=len(state["found"])):
        data = complete_json(render_prompt(
            "ask_step", user_name=state["user_name"], question=state["question"],
            queries="\n".join(f"- {q}" for q in state["queries"]), untrusted_note=note,
            emails=marked,
            must_answer="this is the last step, so you must answer now" if last_chance
            else "you have searched enough"), state["opts"], schema=schemas.ASK_STEP, name="ask_step")
    query = str(data.get("query", "")).strip()
    wants_search = data.get("action") == "search" and query and query not in state["queries"]
    if wants_search and not last_chance:
        return {"next_query": query}
    answer = security.unmark(str(data.get("answer", ""))).strip()
    return {"answer": answer or "I could not find that in your inbox.",
            "mail_ids": [i for i in data.get("mail_ids", []) if i in state["found"]]}


def route(state: AskState) -> str:
    return "done" if state.get("answer") else "search"


def build():
    graph = StateGraph(AskState)
    graph.add_node("search", search)
    graph.add_node("decide", decide)
    graph.add_edge(START, "search")
    graph.add_edge("search", "decide")
    graph.add_conditional_edges("decide", route, {"search": "search", "done": END})
    return graph.compile()


ASK_GRAPH = build()


def run_ask_graph(question: str, retriever: Retriever, user_name: str, opts: LLMOptions) -> AskAnswer:
    with span("graph.ask") as s:
        final = ASK_GRAPH.invoke({"question": question, "user_name": user_name, "opts": opts,
                                  "retriever": retriever, "next_query": question})
        s.set_attribute("searches", len(final["queries"]))
        s.set_attribute("cited", len(final.get("mail_ids", [])))
    found = final["found"]
    return AskAnswer(
        answer=final["answer"],
        citations=[Citation(mail_id=m.id, subject=m.subject, sender=m.sender,
                            received_at=m.received_at)
                   for m in (found[i] for i in dict.fromkeys(final.get("mail_ids", [])))],
        searches=final["queries"],
        model=opts.model,
    )
