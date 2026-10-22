"""Mail classification: an LLM classifier and a keyword classifier (instant fallback + eval baseline)."""
import re

from app.llm.client import complete_json, render_prompt
from app.models import Classification, LLMOptions, Mail

CATEGORY_DESCRIPTIONS = {
    "Placement": "the college placement / career cell: campus drives, drive registrations, "
                 "eligibility and shortlist announcements, placement rules, pre-placement talks.",
    "HR/Recruiter": "a company's HR team or a recruiter writing directly about one application: "
                    "interview scheduling, online assessments, offers, documents, onboarding.",
    "Academic": "courses, assignments, exams, grades, professors, TAs, timetable, fees and "
                "university administration.",
    "Project": "team projects, research, open-source, hackathons or side projects the student "
               "works on: code reviews, meetings, task updates.",
    "Other": "newsletters, promotions, social events, account notifications and anything else.",
}

# Written from general knowledge of student mail, before looking at the sample set.
KEYWORDS = {
    "Placement": ["placement", "campus drive", "placement cell", "career cell", "career services",
                  "tpo", "eligib", "pre-placement", "drive", "shortlist", "batch", "ctc"],
    "HR/Recruiter": ["interview", "recruiter", "talent acquisition", "offer letter", "hiring",
                     "assessment", "candidate", "position", "role", "onboarding", "joining",
                     "background verification", "hr"],
    "Academic": ["assignment", "exam", "midterm", "quiz", "lecture", "course", "professor",
                 "semester", "grade", "lab", "syllabus", "attendance", "thesis", "registrar",
                 "timetable", "tutorial", "viva", "fee"],
    "Project": ["project", "repo", "pull request", "github", "hackathon", "sprint", "standup",
                "merge", "prototype", "demo", "research", "dataset", "deploy", "bug"],
}
REPLY_CUES = re.compile(
    r"please (reply|confirm|let (me|us) know|share|send|respond)|let (me|us) know|could you|"
    r"can you|kindly (confirm|reply|share)|revert|your availability|are you available",
    re.IGNORECASE,
)
URGENT_CUES = re.compile(r"urgent|asap|today|tomorrow|within 24 hours|\beod\b", re.IGNORECASE)


def _hits(words: list[str], text: str) -> int:
    return sum(1 for w in words if re.search(r"\b" + re.escape(w), text))


def keyword_classify(mail: Mail, categories: list[str] | None = None) -> Classification:
    subject, body = mail.subject.lower(), mail.body.lower()
    scores = {
        cat: 2 * _hits(words, subject) + _hits(words, body)
        for cat, words in KEYWORDS.items()
        if categories is None or cat in categories
    }
    if any(w in mail.sender for w in ("placement", "career", "tpo")):
        scores["Placement"] = scores.get("Placement", 0) + 3
    best = max(scores, key=scores.get) if scores else "Other"
    category = best if scores.get(best, 0) >= 2 else "Other"

    is_bulk = "unsubscribe" in body
    needs_reply = bool(REPLY_CUES.search(mail.body)) and not is_bulk
    if URGENT_CUES.search(mail.subject + " " + mail.body) and category != "Other":
        priority = "high"
    else:
        priority = "medium" if needs_reply else "low"
    return Classification(category=category, priority=priority, needs_reply=needs_reply,
                          reason="keyword match", method="keywords")


def llm_classify(mail: Mail, opts: LLMOptions, categories: list[str]) -> Classification:
    category_text = "\n".join(
        f"- {c}: {CATEGORY_DESCRIPTIONS.get(c, 'user-defined category')}" for c in categories
    )
    prompt = render_prompt(
        "classify", categories=category_text, sender=f"{mail.sender_name} <{mail.sender}>",
        subject=mail.subject, received_at=mail.received_at.isoformat(), body=mail.body[:4000],
    )
    data = complete_json(prompt, opts)

    by_lower = {c.lower(): c for c in categories}
    category = by_lower.get(str(data.get("category", "")).strip().lower(), "Other")
    priority = str(data.get("priority", "medium")).lower()
    if priority not in ("high", "medium", "low"):
        priority = "medium"
    return Classification(
        category=category,
        priority=priority,
        needs_reply=data.get("needs_reply") in (True, "true", "True"),
        reason=str(data.get("reason", ""))[:200],
        method="llm",
    )
