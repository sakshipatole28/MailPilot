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
litellm.suppress_debug_info = True  # its banner would print request details to the console
PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

RETRYABLE = (
    litellm.exceptions.RateLimitError,
    litellm.exceptions.Timeout,
    litellm.exceptions.APIConnectionError,
    litellm.exceptions.ServiceUnavailableError,
    litellm.exceptions.InternalServerError,
    litellm.exceptions.APIError,  # litellm also wraps DNS and network failures in this
)


class LLMError(RuntimeError):
    pass


# In-memory usage counters per model, served by GET /metrics.
METRICS: dict[str, dict[str, float]] = {}


def _count(model: str, **values) -> None:
    m = METRICS.setdefault(model, {"calls": 0, "cache_hits": 0, "errors": 0, "retries": 0,
                                   "latency_ms": 0.0, "prompt_tokens": 0, "completion_tokens": 0})
    for key, value in values.items():
        m[key] += value


def render_prompt(name: str, **values) -> str:
    """Fill prompts/<name>.txt. Uses $placeholders so JSON braces in prompts need no escaping."""
    template = Template((PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8"))
    return template.substitute(**values)


def parse_json(text: str) -> dict:
    """Pull the first {...} object out of a model reply (handles ```json fences and chatter)."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)  # reasoning models' scratchpad
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise LLMError("Model reply contained no JSON object")
    try:
        return json.loads(match.group(0), strict=False)  # allow raw newlines in strings
    except json.JSONDecodeError as e:
        raise LLMError(f"Model reply was not valid JSON: {e}") from e


def _cache_key(model: str, messages: list[dict]) -> str:
    return hashlib.sha256(json.dumps([model, messages], sort_keys=True).encode()).hexdigest()


def complete(prompt: str, opts: LLMOptions, use_cache: bool = True) -> str:
    messages = [{"role": "user", "content": prompt}]
    key = _cache_key(opts.model, messages)
    if use_cache and (cached := db.cache_get(key)) is not None:
        _count(opts.model, cache_hits=1)
        return cached

    kwargs = {"model": opts.model, "messages": messages, "temperature": 0,
              "timeout": settings.llm_timeout}
    if opts.api_key:
        kwargs["api_key"] = opts.api_key
    if opts.model.startswith("ollama/"):
        kwargs["api_base"] = settings.ollama_api_base

    text = ""
    for attempt in range(settings.llm_retries + 1):
        started = time.monotonic()
        try:
            response = litellm.completion(**kwargs)
            text = response.choices[0].message.content or ""
            usage = getattr(response, "usage", None)
            _count(opts.model, calls=1, latency_ms=(time.monotonic() - started) * 1000,
                   prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                   completion_tokens=getattr(usage, "completion_tokens", 0) or 0)
        except RETRYABLE as e:
            _count(opts.model, retries=1)
            if attempt == settings.llm_retries:
                _count(opts.model, errors=1)
                raise LLMError(f"{opts.model} failed after retries: {type(e).__name__}") from e
            wait = min(2 ** attempt * 2, 30)
            log.warning("%s: %s (%s), retrying in %ss", opts.model, type(e).__name__,
                        str(e)[:120].replace("\n", " "), wait)
            time.sleep(wait)
            continue
        except Exception as e:  # auth errors, bad model name, ...: retrying won't help
            _count(opts.model, errors=1)
            raise LLMError(f"{opts.model}: {type(e).__name__}: {str(e)[:200]}") from e
        if text.strip():
            break
        # Reasoning models occasionally return an empty answer; asking again usually works.
        log.warning("%s: empty reply, retrying", opts.model)

    if use_cache and text.strip():  # never cache an empty reply
        db.cache_put(key, text)
    return text


def complete_json(prompt: str, opts: LLMOptions) -> dict:
    """complete() + parse_json(), asking once more if the reply is not valid JSON."""
    try:
        return parse_json(complete(prompt, opts))
    except LLMError:
        retry = prompt + "\n\nYour previous reply was not valid JSON. Reply again with only valid JSON."
        return parse_json(complete(retry, opts))
