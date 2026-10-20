"""Deadline extraction: LLM returns structured JSON, we validate every item before trusting it."""
import re
from datetime import datetime, timedelta

from app.llm.client import complete, parse_json, render_prompt
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
        sender=mail.sender,
        subject=mail.subject,
        body=mail.body[:4000],
    )
    data = parse_json(complete(prompt, opts))
    return validate_deadlines(data.get("deadlines", []), mail)
