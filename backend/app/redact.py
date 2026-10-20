"""Strip personal data from log lines. Mail bodies are never logged; this is a second line of defense."""
import logging
import re

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")
# A capitalized name right after a greeting or sign-off: "Hi Priya", "Regards, Amit Shah"
NAME_AFTER_CUE = re.compile(
    r"\b(Hi|Hello|Dear|Hey|Regards,?|Thanks,?|Sincerely,?|Best,?)(\s+)([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)"
)


def redact(text: str) -> str:
    text = EMAIL.sub("[email]", text)
    text = PHONE.sub("[phone]", text)
    return NAME_AFTER_CUE.sub(lambda m: f"{m.group(1)}{m.group(2)}[name]", text)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


def setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RedactingFilter())
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger("mailpilot")
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    root.propagate = False
