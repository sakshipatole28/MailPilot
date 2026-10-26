"""Triage: one LLM call per mail decides category, intents, importance, summary, tasks and a
phishing opinion. Deterministic code then validates the output (category must exist, every
task needs evidence quoted from the mail, dates are parsed), adds header-based security checks
and computes the explainable priority score.

One call instead of separate classify + extract calls roughly halves the tokens spent per mail,
which matters on free-tier rate limits (see results/ for the measured comparison).
"""
from app.config import settings
from app.llm import priority, security
from app.llm.client import complete_json, render_prompt
from app.llm.deadlines import calendar_lines, evidence_found, validate_deadlines
from app.llm.taxonomy import INTENTS, describe, match_category
from app.models import Category, Deadline, LLMOptions, Mail, Triage
from app.rag.retriever import tokenize


def pick_examples(mail: Mail, corrected: list[Mail], k: int = 4) -> list[Mail]:
    """The user's past category corrections most similar to this mail (few-shot personalization)."""
    # Plain word overlap: BM25's IDF is meaningless with only a handful of corrections.
    words = set(tokenize(f"{mail.sender} {mail.subject}"))
    scored = [(len(words & set(tokenize(f"{m.sender} {m.subject}"))), m)
              for m in corrected if m.id != mail.id]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [m for overlap, m in scored[:k] if overlap > 0]


def format_examples(examples: list[Mail]) -> str:
    if not examples:
        return ""
    lines = "\n".join(f'- From {m.sender}, subject "{m.subject[:80]}" -> {m.category}' for m in examples)
    return f"\nThe user corrected these categories before; follow the same judgment:\n{lines}\n"


def parse_triage(data: dict, categories: list[Category]) -> Triage:
    """Validate the model's JSON into a Triage, repairing what can be repaired."""
    try:
        importance = int(float(data.get("importance", 50)))
    except (TypeError, ValueError):
        importance = 50
    intents = [i for i in data.get("intents", []) if isinstance(i, str) and i.lower() in INTENTS]
    items = [i for i in data.get("action_items", []) if isinstance(i, dict) and i.get("task")]
    return Triage(
        category=match_category(str(data.get("category", "")), categories),
        intents=sorted({i.lower() for i in intents}) or ["fyi"],
        importance=max(0, min(importance, 100)),
        summary=security.unmark(str(data.get("summary", "")))[:240],
        action_items=[{"task": security.unmark(str(i["task"]))[:120],
                       "due_iso": i.get("due_iso") or None,
                       "evidence": str(i.get("evidence", ""))[:300]} for i in items],
        suspicious=data.get("suspicious") in (True, "true", "True"),
        suspicious_reasons=[str(r)[:120] for r in data.get("suspicious_reasons", [])][:3],
    )


def tasks_from(triage: Triage, mail: Mail) -> list[Deadline]:
    """Dated items go through the deadline validator; undated ones only need their evidence."""
    dated = validate_deadlines([{"title": a.task, "due_iso": a.due_iso, "evidence": a.evidence,
                                 "confidence": 0.8} for a in triage.action_items if a.due_iso], mail)
    text = f"{mail.subject}\n{mail.body}"
    undated = [Deadline(mail_id=mail.id, title=a.task, evidence=a.evidence[:300], confidence=0.8)
               for a in triage.action_items
               if not a.due_iso and evidence_found(a.evidence, text)]
    return dated + undated


def triage_mail(mail: Mail, opts: LLMOptions, categories: list[Category], user_name: str,
                corrected: list[Mail] = (), known_senders: set[str] = frozenset(),
                spotlight_mode: str | None = None) -> tuple[Mail, list[Deadline]]:
    """Return the mail with triage fields filled in, plus the tasks found in it."""
    body, note = security.spotlight(mail.body[:4000], spotlight_mode or settings.spotlight)
    prompt = render_prompt(
        "triage",
        user_name=user_name,
        categories=describe(categories),
        intents="\n".join(f"- {k}: {v}" for k, v in INTENTS.items()),
        received_at=mail.received_at.isoformat(),
        weekday=mail.received_at.strftime("%A"),
        calendar=calendar_lines(mail.received_at),
        examples=format_examples(pick_examples(mail, list(corrected))),
        untrusted_note=note,
        sender=f"{mail.sender_name} <{mail.sender}>",
        to=mail.to[:200],
        subject=mail.subject,
        body=body,
    )
    triage = parse_triage(complete_json(prompt, opts), categories)
    tasks = tasks_from(triage, mail)

    known_domains = {security.registrable(security.domain_of(s)) for s in known_senders}
    risk_level, risk_reasons = security.assess(mail, triage.suspicious, triage.suspicious_reasons,
                                               known_domains)
    points, reasons = priority.score(mail, triage.importance, triage.intents, tasks,
                                     mail.sender in known_senders, risk_level)
    updated = mail.model_copy(update={
        "category": triage.category,
        "classified_by": "llm",
        "intents": triage.intents,
        "needs_reply": "reply" in triage.intents,
        "summary": triage.summary,
        "priority_score": points,
        "priority": priority.label(points),
        "priority_reasons": reasons,
        "risk_level": risk_level,
        "risk_reasons": risk_reasons,
        "triage_status": "done",
    })
    return updated, tasks
