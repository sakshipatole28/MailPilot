"""Priority score (0-100) with human-readable reasons.

Gmail's Priority Inbox (Aberdeen, Pacovsky & Slater, 2010) found social signals, such as whether
you reply to a sender, among the strongest predictors of importance, alongside content. We blend
the LLM's content judgment with a few such signals, so every score can be explained in a line.
"""
from datetime import datetime, timedelta, timezone

from app.models import Deadline, Mail

BULK_LABELS = {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_FORUMS"}


def is_bulk(mail: Mail) -> bool:
    """Mass mail: has an unsubscribe/list header, bulk precedence or a Gmail bulk tab."""
    h = mail.headers
    return bool(h.get("list_unsubscribe") or h.get("list_id")
                or h.get("precedence", "").lower() in ("bulk", "list", "junk")
                or BULK_LABELS & set(mail.labels)
                or "unsubscribe" in mail.body.lower())


def score(mail: Mail, importance: int, intents: list[str], tasks: list[Deadline],
          known_sender: bool, risk_level: str, now: datetime | None = None) -> tuple[int, list[str]]:
    now = now or datetime.now(timezone.utc)
    points = round(0.6 * max(0, min(importance, 100)))
    reasons = [f"AI importance {importance}/100"]

    def add(delta: int, reason: str):
        nonlocal points
        points += delta
        reasons.append(reason)

    if "reply" in intents:
        add(15, "Expects your reply")
    elif "task" in intents or "meeting" in intents:
        add(10, "Asks you to do something")
    soon = [t for t in tasks if t.due_iso and
            now - timedelta(hours=12) <= datetime.fromisoformat(t.due_iso) <= now + timedelta(hours=48)]
    if soon:
        add(15, "Deadline within 48 hours")
    if known_sender:
        add(10, "You have replied to this sender before")
    if is_bulk(mail):
        add(-25, "Mass mail (newsletter or marketing)")
    if risk_level == "high":
        add(-40, "Looks like phishing")
    return max(0, min(100, points)), reasons


def label(points: int) -> str:
    return "high" if points >= 70 else "medium" if points >= 40 else "low"
