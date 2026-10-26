"""Pydantic models shared by the API and the services."""
from datetime import datetime

from pydantic import BaseModel, Field


class Mail(BaseModel):
    id: str
    thread_id: str | None = None
    sender: str
    sender_name: str = ""
    to: str = ""
    subject: str
    body: str
    received_at: datetime
    is_read: bool = False
    replied: bool = False
    category: str | None = None
    priority: str | None = None
    needs_reply: bool | None = None
    classified_by: str | None = None  # "keywords", "llm" or "user" (a correction)
    # Raw signals from the message, used by priority and security checks
    headers: dict[str, str] = {}  # auth_results, reply_to, list_unsubscribe, list_id, precedence ...
    labels: list[str] = []  # Gmail label ids, e.g. CATEGORY_PROMOTIONS
    links: list[str] = []  # URLs found in the message (including HTML hrefs)
    # Filled in by triage
    summary: str = ""
    intents: list[str] = []  # reply, task, meeting, fyi
    priority_score: int | None = None
    priority_reasons: list[str] = []
    risk_level: str | None = None  # low, medium, high
    risk_reasons: list[str] = []
    triage_status: str | None = None  # pending, done, failed


class MailUpdate(BaseModel):
    is_read: bool | None = None
    replied: bool | None = None
    category: str | None = None  # a user correction; also teaches the classifier


class Category(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=400)


class ActionItem(BaseModel):
    task: str
    due_iso: str | None = None
    evidence: str = ""


class Triage(BaseModel):
    """Everything one LLM call decides about a mail."""
    category: str
    intents: list[str] = []
    importance: int = 50
    summary: str = ""
    action_items: list[ActionItem] = []
    suspicious: bool = False
    suspicious_reasons: list[str] = []


class LLMOptions(BaseModel):
    model: str
    api_key: str | None = None


class ClassifyRequest(BaseModel):
    mail_id: str


class Classification(BaseModel):
    category: str
    priority: str = "low"
    needs_reply: bool = False
    reason: str = ""
    method: str = "llm"  # "llm" or "keywords"


class Deadline(BaseModel):
    """A task from a mail. Tasks with a due date get reminders; undated ones are a to-do list."""
    id: int | None = None
    mail_id: str
    title: str
    due_iso: str | None = None
    confidence: float = 0.0
    evidence: str = ""
    done: bool = False
    mail_subject: str | None = None


class DeadlineExtractRequest(BaseModel):
    mail_id: str


class DeadlineUpdate(BaseModel):
    done: bool


class SourceChunk(BaseModel):
    id: str
    text: str
    source: str
    title: str = ""
    score: float = 0.0


class DraftRequest(BaseModel):
    mail_id: str
    tone: str | None = None
    instruction: str = ""
    use_rag: bool = True


class ComposeRequest(BaseModel):
    instruction: str = Field(min_length=3)
    tone: str | None = None
    use_rag: bool = True


class GeneratedEmail(BaseModel):
    draft_id: int | None = None
    subject: str
    body: str
    sources: list[SourceChunk] = []
    issues: list[str] = []
    quick_replies: list[str] = []
    model: str = ""


class Feedback(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = ""


class AppSettings(BaseModel):
    model: str
    tone: str
    categories: list[Category]
    local_only: bool
    user_name: str
    auto_triage: bool
    suggested_models: list[str] = []
    presets: dict[str, list[Category]] = {}


class SettingsUpdate(BaseModel):
    model: str | None = None
    tone: str | None = None
    categories: list[Category] | None = Field(default=None, min_length=1, max_length=25)
    local_only: bool | None = None
    user_name: str | None = None
    auto_triage: bool | None = None


class TriageRequest(BaseModel):
    mail_ids: list[str] | None = None  # None = every mail not triaged yet
    limit: int = Field(default=10, ge=1, le=100)


class Citation(BaseModel):
    mail_id: str
    subject: str
    sender: str
    received_at: datetime


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class AskAnswer(BaseModel):
    answer: str
    citations: list[Citation] = []
    model: str = ""


class Brief(BaseModel):
    """The "Today" card: what needs attention, computed from triage results (no LLM call)."""
    needs_reply: list[Mail] = []
    due_soon: list["Deadline"] = []
    suspicious: list[Mail] = []
    unread: int = 0
    pending_triage: int = 0
