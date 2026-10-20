"""Deterministic checks on generated drafts.

Every date, time, weekday, URL, email address or phone number in a draft must also appear in the
source text (incoming mail + retrieved context + user instruction). Anything else is replaced by
a "[confirm: ...]" placeholder and reported as an issue.
"""
import re
from dataclasses import dataclass, field

MONTH = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
         r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")

# One alternation, longest forms first, so a single pass never wraps the same text twice.
CHECKS = re.compile(
    "|".join([
        r"(?P<url>https?://[^\s)\]>]+|www\.[^\s)\]>]+)",
        r"(?P<email>[\w.+-]+@[\w-]+\.[\w.-]+)",
        rf"(?P<date>\b\d{{1,2}}(?:st|nd|rd|th)?\s+{MONTH}\b(?:,?\s+\d{{4}})?"
        rf"|\b{MONTH}\s+\d{{1,2}}(?:st|nd|rd|th)?\b(?:,?\s+\d{{4}})?"
        r"|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b)",
        r"(?P<time>\b\d{1,2}(?::\d{2})?\s?(?:am|pm)\b|\b\d{1,2}:\d{2}\b)",
        r"(?P<weekday>\b(?:mon|tues|wednes|thurs|fri|satur|sun)day\b)",
        r"(?P<phone>(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w))",
    ]),
    re.IGNORECASE,
)
GREETING = re.compile(r"^\s*(?i:hi|hello|dear|hey)\s+([A-Z][a-zA-Z]+)")


def _norm(text: str) -> str:
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text.lower())
    return re.sub(r"\s+", " ", text).strip().rstrip(".,")


@dataclass
class GuardrailResult:
    text: str
    issues: list[str] = field(default_factory=list)


def check_draft(draft: str, source_text: str) -> GuardrailResult:
    source = _norm(source_text)
    issues: list[str] = []

    def replace(m: re.Match) -> str:
        value = m.group(0)
        if _norm(value) in source:
            return value
        if m.start() >= 9 and m.string[m.start() - 9:m.start()].lower() == "[confirm:":
            return value  # already a placeholder
        issues.append(f"Unsupported {m.lastgroup} '{value.strip()}' replaced with a placeholder")
        return f"[confirm: {value.strip()}]"

    text = CHECKS.sub(replace, draft)

    greeting = GREETING.match(text)
    if greeting and greeting.group(1).lower() not in source:
        name = greeting.group(1)
        issues.append(f"Greeting name '{name}' is not in the mail; check it")
        text = text[:greeting.start(1)] + "[name]" + text[greeting.end(1):]

    return GuardrailResult(text=text, issues=issues)
