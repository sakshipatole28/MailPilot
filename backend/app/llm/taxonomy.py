"""Category presets. Categories are plain-language descriptions, so users can add their own
("Anything from my landlord") the same way Superhuman's Auto Labels work: the LLM reads the
description, so no training data is needed.

Categories say what a mail is *about*. What it asks of the user is a separate, fixed set of
intents (reply / task / meeting / fyi), following the information-exchange, task-management,
scheduling and social split used in email-intent research (Shu et al., SIGIR 2020)."""
from app.models import Category

INTENTS = {
    "reply": "the sender expects a written reply from the user",
    "task": "the user has to do something other than reply (submit, pay, sign, register, review)",
    "meeting": "it proposes, schedules, moves or confirms a meeting, call, interview or event",
    "fyi": "information only; nothing to do",
}

GENERAL = [
    Category(name="Work & Career", description="Jobs, recruiters, interviews, offers, colleagues, "
             "clients, internships and anything about the user's work or job search."),
    Category(name="Education", description="Courses, classes, exams, assignments, grades, "
             "professors, school or university administration."),
    Category(name="Projects", description="Side projects, open source, research, hackathons and "
             "team collaboration: code reviews, issues, task updates."),
    Category(name="Finance & Bills", description="Banks, cards, statements, bills, payments due, "
             "taxes, salary, insurance, investments."),
    Category(name="Purchases & Deliveries", description="Orders, receipts, invoices for "
             "purchases, shipping and delivery updates, returns and refunds."),
    Category(name="Travel & Events", description="Flight, train and hotel bookings, tickets, "
             "itineraries, event invitations and RSVPs."),
    Category(name="Accounts & Security", description="Sign-in alerts, verification codes, "
             "password resets, account and service notices, subscription renewals."),
    Category(name="Personal", description="Family, friends and other personal one-to-one mail."),
    Category(name="Newsletters", description="Newsletters, digests, blogs and product updates "
             "the user subscribed to."),
    Category(name="Promotions", description="Marketing, sales, discounts, offers and cold pitches."),
    Category(name="Social & Community", description="Social networks, forums, clubs, communities "
             "and group announcements."),
    Category(name="Other", description="Anything that fits none of the categories above."),
]

STUDENT = [
    Category(name="Placement", description="The college placement / career cell: campus drives, "
             "drive registrations, eligibility and shortlist announcements, placement rules, "
             "pre-placement talks."),
    Category(name="HR/Recruiter", description="A company's HR team or a recruiter writing "
             "directly about one application: interview scheduling, online assessments, offers, "
             "documents, onboarding."),
    Category(name="Academic", description="Courses, assignments, exams, grades, professors, TAs, "
             "timetable, fees and university administration."),
    Category(name="Project", description="Team projects, research, open-source, hackathons or "
             "side projects the student works on: code reviews, meetings, task updates."),
    Category(name="Other", description="Newsletters, promotions, social events, account "
             "notifications and anything else."),
]

PRESETS = {"general": GENERAL, "student": STUDENT}


def describe(categories: list[Category]) -> str:
    return "\n".join(f"- {c.name}: {c.description or 'user-defined category'}" for c in categories)


def match_category(name: str, categories: list[Category]) -> str:
    """Map a model's answer onto a configured category name (case-insensitive), else Other."""
    by_lower = {c.name.lower(): c.name for c in categories}
    fallback = by_lower.get("other", categories[-1].name)
    return by_lower.get(str(name).strip().lower(), fallback)


def from_stored(value) -> list[Category]:
    """Settings saved by older versions are a list of names; give known names their description."""
    known = {c.name: c for preset in PRESETS.values() for c in preset}
    out = []
    for item in value:
        if isinstance(item, str):
            out.append(known.get(item, Category(name=item)))
        else:
            out.append(Category(**item))
    return out
