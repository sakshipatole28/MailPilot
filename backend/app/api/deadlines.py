from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app import db
from app.api.mail import get_mail_or_404
from app.deps import llm_options
from app.jobs import run_triage
from app.models import Deadline, DeadlineExtractRequest, DeadlineUpdate, LLMOptions

router = APIRouter(tags=["tasks"])


@router.post("/deadlines/extract", response_model=list[Deadline])
def extract(req: DeadlineExtractRequest, opts: LLMOptions = Depends(llm_options)):
    """Find the tasks and deadlines in one mail (runs triage, which extracts them)."""
    get_mail_or_404(req.mail_id)
    _, failed = run_triage([req.mail_id], opts)
    if failed:
        raise HTTPException(502, "Triage failed; see the backend log")
    return db.list_deadlines(include_done=True, mail_id=req.mail_id)


@router.get("/deadlines", response_model=list[Deadline])
def list_deadlines(include_done: bool = False):
    return db.list_deadlines(include_done=include_done)


@router.patch("/deadlines/{deadline_id}")
def update_deadline(deadline_id: int, update: DeadlineUpdate):
    if not db.set_deadline_done(deadline_id, update.done):
        raise HTTPException(404, "Deadline not found")
    return {"id": deadline_id, "done": update.done}


def _ics_text(value: str) -> str:
    return (value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\n", "\\n"))


def to_ics(tasks: list[Deadline]) -> str:
    """RFC 5545 calendar with one event per dated task and a reminder a day before."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//MailPilot//Tasks//EN",
             "CALSCALE:GREGORIAN"]
    for t in tasks:
        if not t.due_iso:
            continue
        due = datetime.fromisoformat(t.due_iso).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        lines += ["BEGIN:VEVENT", f"UID:task-{t.id}@mailpilot", f"DTSTAMP:{stamp}",
                  f"DTSTART:{due}", f"DTEND:{due}", f"SUMMARY:{_ics_text(t.title)}",
                  f"DESCRIPTION:{_ics_text('From: ' + (t.mail_subject or ''))}",
                  "BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_ics_text(t.title)}",
                  "TRIGGER:-P1D", "END:VALARM", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


@router.get("/deadlines.ics")
def deadlines_ics():
    """Open tasks as a calendar file for Google Calendar, Outlook or Apple Calendar."""
    return Response(to_ics(db.list_deadlines()), media_type="text/calendar",
                    headers={"Content-Disposition": "attachment; filename=mailpilot-tasks.ics"})
