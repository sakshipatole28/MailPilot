from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import db
from app.api import compose, deadlines, draft, mail, rag
from app.api import settings as settings_api
from app.llm.client import LLMError
from app.redact import setup_logging

setup_logging()
db.init_db()

app = FastAPI(title="MailPilot", description="Drafts only. Nothing is ever sent.")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"chrome-extension://.*|http://localhost(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)
for module in (mail, deadlines, draft, compose, rag, settings_api):
    app.include_router(module.router)


@app.exception_handler(LLMError)
def llm_error(_: Request, exc: LLMError):
    # 502: the upstream model failed (no key, rate limit after retries, bad JSON)
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.get("/health")
def health():
    return {"ok": True}
