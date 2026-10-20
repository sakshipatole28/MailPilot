"""App settings, read from environment / .env (see .env.example)."""
from pathlib import Path

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]  # repo root

# Put provider keys (GEMINI_API_KEY, ...) into os.environ, where LiteLLM looks for them.
load_dotenv(ROOT / ".env")

DEFAULT_CATEGORIES = ["Placement", "HR/Recruiter", "Academic", "Project", "Other"]

SUGGESTED_MODELS = [
    "gemini/gemini-2.5-flash",
    "groq/llama-3.3-70b-versatile",
    "ollama/qwen2.5:7b",
    "gpt-4o-mini",
    "anthropic/claude-sonnet-4-5",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    model: str = "gemini/gemini-2.5-flash"
    ollama_api_base: str = "http://localhost:11434"
    llm_retries: int = 3
    llm_timeout: int = 60

    db_path: Path = ROOT / "data" / "mailpilot.db"
    chroma_dir: Path = ROOT / "data" / "chroma"
    context_dir: Path = ROOT / "data" / "context"

    mail_source: str = "file"
    mail_file: Path = ROOT / "data" / "sample_mails.json"
    gmail_credentials: Path = ROOT / "secrets" / "credentials.json"
    gmail_token: Path = ROOT / "secrets" / "token.json"
    gmail_max: int = 50

    embed_model: str = "BAAI/bge-small-en-v1.5"
    rerank: bool = False
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    top_k: int = 4

    user_name: str = "Sam Rivera"
    tone: str = "friendly and professional"
    local_only: bool = False

    @field_validator("db_path", "chroma_dir", "context_dir", "mail_file",
                     "gmail_credentials", "gmail_token")
    @classmethod
    def _relative_to_root(cls, p: Path) -> Path:
        return p if p.is_absolute() else ROOT / p


settings = Settings()
