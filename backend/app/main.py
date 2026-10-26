from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import db
from app.api import ask, compose, deadlines, draft, mail, rag
from app.api import settings as settings_api
from app.jobs import worker
from app.llm.client import METRICS, LLMError
from app.redact import setup_logging

setup_logging()
db.init_db()


@asynccontextmanager
async def lifespan(_: FastAPI):
    worker.start()  # background triage of newly synced mail
    yield


app = FastAPI(title="MailPilot", description="Drafts only. Nothing is ever sent.",
              lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    # Only browser extensions may call the API from a browser: an ordinary web page the user
    # visits cannot read their mail through localhost.
    allow_origin_regex=r"(chrome|moz)-extension://.*",
    allow_methods=["*"],
    allow_headers=["*"],
)
for module in (mail, deadlines, draft, compose, ask, rag, settings_api):
    app.include_router(module.router)


@app.exception_handler(LLMError)
def llm_error(_: Request, exc: LLMError):
    # 502: the upstream model failed (no key, rate limit after retries, bad JSON)
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/metrics")
def metrics():
    """LLM usage since startup (per model) and the triage backlog."""
    models = {}
    for model, m in METRICS.items():
        calls = m["calls"]
        lookups = calls + m["cache_hits"]
        models[model] = {**{k: round(v) for k, v in m.items()},
                         "avg_latency_ms": round(m["latency_ms"] / calls) if calls else 0,
                         "cache_hit_rate": round(m["cache_hits"] / lookups, 3) if lookups else 0}
    return {"llm": models, "triage": db.triage_counts(), "queued": worker.pending()}
