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
    classified_by: str | None = None


class MailUpdate(BaseModel):
    is_read: bool | None = None
    replied: bool | None = None


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
    id: int | None = None
    mail_id: str
    title: str
    due_iso: str
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
    model: str = ""


class Feedback(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = ""


class AppSettings(BaseModel):
    model: str
    tone: str
    categories: list[str]
    local_only: bool
    user_name: str
    suggested_models: list[str] = []


class SettingsUpdate(BaseModel):
    model: str | None = None
    tone: str | None = None
    categories: list[str] | None = None
    local_only: bool | None = None
    user_name: str | None = None
