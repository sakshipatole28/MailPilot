"""Thin LiteLLM wrapper: one call for every provider, with retry + response cache."""
import hashlib
import json
import logging
import re
import time
from pathlib import Path
from string import Template

import litellm

from app import db
from app.config import settings
from app.models import LLMOptions

log = logging.getLogger("mailpilot.llm")
PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

RETRYABLE = (
    litellm.exceptions.RateLimitError,
    litellm.exceptions.Timeout,
    litellm.exceptions.APIConnectionError,
    litellm.exceptions.ServiceUnavailableError,
    litellm.exceptions.InternalServerError,
)


class LLMError(RuntimeError):
    pass


def render_prompt(name: str, **values) -> str:
    """Fill prompts/<name>.txt. Uses $placeholders so JSON braces in prompts need no escaping."""
    template = Template((PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8"))
    return template.substitute(**values)


def parse_json(text: str) -> dict:
    """Pull the first {...} object out of a model reply (handles ```json fences and chatter)."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise LLMError("Model reply contained no JSON object")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise LLMError(f"Model reply was not valid JSON: {e}") from e


def _cache_key(model: str, messages: list[dict]) -> str:
    return hashlib.sha256(json.dumps([model, messages], sort_keys=True).encode()).hexdigest()


def complete(prompt: str, opts: LLMOptions, use_cache: bool = True) -> str:
    messages = [{"role": "user", "content": prompt}]
    key = _cache_key(opts.model, messages)
    if use_cache and (cached := db.cache_get(key)) is not None:
        return cached

    kwargs = {"model": opts.model, "messages": messages, "temperature": 0,
              "timeout": settings.llm_timeout}
    if opts.api_key:
        kwargs["api_key"] = opts.api_key
    if opts.model.startswith("ollama/"):
        kwargs["api_base"] = settings.ollama_api_base

    for attempt in range(settings.llm_retries + 1):
        try:
            response = litellm.completion(**kwargs)
            break
        except RETRYABLE as e:
            if attempt == settings.llm_retries:
                raise LLMError(f"{opts.model} failed after retries: {type(e).__name__}") from e
            wait = 2 ** attempt * 2
            log.warning("%s: %s, retrying in %ss", opts.model, type(e).__name__, wait)
            time.sleep(wait)
        except Exception as e:  # auth errors, bad model name, ...: retrying won't help
            raise LLMError(f"{opts.model}: {type(e).__name__}: {str(e)[:200]}") from e

    text = response.choices[0].message.content or ""
    if use_cache:
        db.cache_put(key, text)
    return text
