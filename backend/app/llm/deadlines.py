"""Deadline extraction: LLM returns structured JSON, we validate every item before trusting it."""
import re
from datetime import datetime, timedelta

from app.llm.client import complete_json, render_prompt
from app.models import Deadline, LLMOptions, Mail


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def evidence_found(evidence: str, text: str, min_overlap: float = 0.8) -> bool:
    """True if most words of the quoted evidence appear in the mail (tolerates small rewording)."""
    ev = _tokens(evidence)
    if not ev:
        return False
    words = set(_tokens(text))
    return sum(t in words for t in ev) / len(ev) >= min_overlap


def calendar_lines(start: datetime, days: int = 21) -> str:
    """'Mon 19 Oct 2026' for the next three weeks. LLMs often get weekday arithmetic wrong
    ("by Sunday" from a Monday), so the prompt gives them the answer to look up instead."""
    return "\n".join((start + timedelta(days=i)).strftime("%a %d %b %Y") +
                      (" (received)" if i == 0 else "") for i in range(days))


def validate_deadlines(items: list, mail: Mail) -> list[Deadline]:
    text = f"{mail.subject}\n{mail.body}"
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            due = datetime.fromisoformat(str(item.get("due_iso", "")))
        except ValueError:
            continue
        if due.tzinfo is None:
            due = due.replace(tzinfo=mail.received_at.tzinfo)
        evidence = str(item.get("evidence", "")).strip()
        if not evidence_found(evidence, text):
            continue  # the model could not point at the words stating this date: likely invented
        if due < mail.received_at - timedelta(days=1):
            continue  # a deadline before the mail arrived means the relative date was misread
        try:
            confidence = min(max(float(item.get("confidence", 0.5)), 0.0), 1.0)
        except (TypeError, ValueError):
            confidence = 0.5
        if any(d.due_iso[:10] == due.date().isoformat() for d in out):
            continue  # one reminder per date per mail; extra items are usually prep steps
        out.append(Deadline(
            mail_id=mail.id,
            title=str(item.get("title") or mail.subject)[:120],
            due_iso=due.isoformat(),
            confidence=confidence,
            evidence=evidence[:300],
        ))
    return out


def extract_deadlines(mail: Mail, opts: LLMOptions) -> list[Deadline]:
    prompt = render_prompt(
        "deadlines",
        received_at=mail.received_at.isoformat(),
        weekday=mail.received_at.strftime("%A"),
        calendar=calendar_lines(mail.received_at),
        sender=mail.sender,
        subject=mail.subject,
        body=mail.body[:4000],
    )
    data = complete_json(prompt, opts)
    return validate_deadlines(data.get("deadlines", []), mail)
