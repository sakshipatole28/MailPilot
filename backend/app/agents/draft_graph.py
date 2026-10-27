"""Self-correcting reply drafts as a LangGraph state machine.

    generate -> check --(unsupported facts and rounds left)--> revise -> check ...
                      \\--(clean, or out of rounds)----------> finalize

The checker is the deterministic guardrail (app/llm/guardrails.py): dates, times, links,
emails, phone numbers and greeting names must appear in the mail, the user's notes or the
instruction. Instead of only masking problems with [confirm: ...], the graph first gives the
model the specific problems and lets it rewrite the sentence properly, the generate -> critique
-> revise pattern ("Self-Refine", Madaan et al., NeurIPS 2023), with a deterministic critic
instead of an LLM one. Whatever survives the last round is still masked by the guardrail, so
the loop can only improve a draft, never make it less safe.
"""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.llm.generator import (_finish, generate_reply, reply_link_source, reply_source_text,
                                revise_reply)
from app.config import settings
from app.llm.guardrails import check_draft
from app.models import GeneratedEmail, LLMOptions, Mail, SourceChunk
from app.tracing import span

MAX_REVISIONS = 2


class DraftState(TypedDict, total=False):
    # inputs
    mail: Mail
    chunks: list[SourceChunk]
    style: list[SourceChunk]
    tone: str
    user_name: str
    instruction: str
    opts: LLMOptions
    spotlight_mode: str | None
    # working state
    subject: str
    body: str
    quick: list[str]
    problems: list[str]
    first_pass_issues: int
    revisions: int
    # output
    result: GeneratedEmail


def _source(state: DraftState) -> str:
    return reply_source_text(state["mail"], state["chunks"], state["instruction"], state["user_name"])


def generate(state: DraftState) -> dict:
    with span("graph.draft.generate", mail_id=state["mail"].id):
        subject, body, quick = generate_reply(
            state["mail"], state["chunks"], state["style"], state["tone"], state["user_name"],
            state["instruction"], state["opts"], state.get("spotlight_mode"))
    return {"subject": subject, "body": body, "quick": quick, "revisions": 0}


def _links(state: DraftState) -> str:
    return reply_link_source(state["mail"], state["chunks"], state["instruction"])


def check(state: DraftState) -> dict:
    source, links = _source(state), _links(state)
    issues = (check_draft(state["subject"], source, links).issues
              + check_draft(state["body"], source, links).issues)
    problems = [i.replace(" replaced with a placeholder", "") for i in issues]
    update = {"problems": problems}
    if state.get("revisions", 0) == 0:
        update["first_pass_issues"] = len(problems)
    return update


def route(state: DraftState) -> str:
    if settings.self_correct and state["problems"] and state.get("revisions", 0) < MAX_REVISIONS:
        return "revise"
    return "finalize"


def revise(state: DraftState) -> dict:
    with span("graph.draft.revise", mail_id=state["mail"].id, problems=len(state["problems"]),
              round=state["revisions"] + 1):
        subject, body = revise_reply(state["mail"], state["chunks"], state["subject"],
                                     state["body"], state["problems"], state["user_name"],
                                     state["opts"], state.get("spotlight_mode"))
    return {"subject": subject, "body": body, "revisions": state["revisions"] + 1}


def finalize(state: DraftState) -> dict:
    result = _finish(state["subject"], state["body"], _source(state), state["chunks"],
                     state["opts"].model, state.get("quick", []), _links(state))
    result.revisions = state.get("revisions", 0)
    result.first_pass_issues = state.get("first_pass_issues", 0)
    return {"result": result}


def build() -> StateGraph:
    graph = StateGraph(DraftState)
    graph.add_node("generate", generate)
    graph.add_node("check", check)
    graph.add_node("revise", revise)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "generate")
    graph.add_edge("generate", "check")
    graph.add_conditional_edges("check", route, {"revise": "revise", "finalize": "finalize"})
    graph.add_edge("revise", "check")
    graph.add_edge("finalize", END)
    return graph.compile()


DRAFT_GRAPH = build()


def run_draft_graph(mail: Mail, chunks: list[SourceChunk], style: list[SourceChunk], tone: str,
                    user_name: str, instruction: str, opts: LLMOptions,
                    spotlight_mode: str | None = None) -> GeneratedEmail:
    with span("graph.draft", mail_id=mail.id) as s:
        final = DRAFT_GRAPH.invoke({
            "mail": mail, "chunks": chunks, "style": style, "tone": tone, "user_name": user_name,
            "instruction": instruction, "opts": opts, "spotlight_mode": spotlight_mode})
        result = final["result"]
        s.set_attribute("revisions", result.revisions)
        s.set_attribute("first_pass_issues", result.first_pass_issues)
        s.set_attribute("final_issues", len(result.issues))
        return result
