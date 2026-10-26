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
from app.tracing import span

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


def _cache_key(model: str, messages: list[dict], schema: dict | None = None) -> str:
    parts = [model, messages] + ([schema] if schema else [])  # old cache entries stay valid
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()


_NO_SCHEMA: set[str] = set()  # models that rejected response_format at runtime


def supports_schema(model: str) -> bool:
    if not settings.structured_outputs or model in _NO_SCHEMA:
        return False
    try:
        return bool(litellm.supports_response_schema(model=model))
    except Exception:  # unknown model: LiteLLM has no capability data
        return False


def complete(prompt: str, opts: LLMOptions, use_cache: bool = True,
             schema: dict | None = None, name: str = "response") -> str:
    """One LLM call. With `schema`, providers that support structured outputs are constrained
    to it (strict JSON schema); others just get the prompt, which also describes the format."""
    with span("llm.complete", model=opts.model, schema=name if schema else None) as s:
        text, cached = _complete(prompt, opts, use_cache, schema, name, s)
        s.set_attribute("cache_hit", cached)
        return text


def _complete(prompt, opts, use_cache, schema, name, s) -> tuple[str, bool]:
    schema = schema if schema and supports_schema(opts.model) else None
    s.set_attribute("structured_output", bool(schema))
    messages = [{"role": "user", "content": prompt}]
    key = _cache_key(opts.model, messages, schema)
    if use_cache and (cached := db.cache_get(key)) is not None:
        _count(opts.model, cache_hits=1)
        return cached, True

    kwargs = {"model": opts.model, "messages": messages, "temperature": 0,
              "timeout": settings.llm_timeout}
    if opts.api_key:
        kwargs["api_key"] = opts.api_key
    if opts.model.startswith("ollama/"):
        kwargs["api_base"] = settings.ollama_api_base
    if schema:
        kwargs["response_format"] = {"type": "json_schema",
                                     "json_schema": {"name": name, "schema": schema, "strict": True}}

    text = ""
    for attempt in range(settings.llm_retries + 1):
        started = time.monotonic()
        try:
            response = litellm.completion(**kwargs)
            text = response.choices[0].message.content or ""
            usage = getattr(response, "usage", None)
            tokens_in = getattr(usage, "prompt_tokens", 0) or 0
            tokens_out = getattr(usage, "completion_tokens", 0) or 0
            _count(opts.model, calls=1, latency_ms=(time.monotonic() - started) * 1000,
                   prompt_tokens=tokens_in, completion_tokens=tokens_out)
            s.set_attribute("prompt_tokens", tokens_in)
            s.set_attribute("completion_tokens", tokens_out)
            s.set_attribute("attempt", attempt)
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
        except litellm.exceptions.BadRequestError as e:
            if schema and "response_format" in str(e).lower() or schema and "schema" in str(e).lower():
                _NO_SCHEMA.add(opts.model)  # provider refused the schema: fall back to prompt-only
                return _complete(prompt, opts, use_cache, None, name, s)
            _count(opts.model, errors=1)
            raise LLMError(f"{opts.model}: {type(e).__name__}: {str(e)[:200]}") from e
        except Exception as e:  # auth errors, bad model name, ...: retrying won't help
            _count(opts.model, errors=1)
            raise LLMError(f"{opts.model}: {type(e).__name__}: {str(e)[:200]}") from e
        if text.strip():
            break
        # Reasoning models occasionally return an empty answer; asking again usually works.
        log.warning("%s: empty reply, retrying", opts.model)

    if use_cache and text.strip():  # never cache an empty reply
        db.cache_put(key, text)
    return text, False


def complete_json(prompt: str, opts: LLMOptions, schema: dict | None = None,
                  name: str = "response") -> dict:
    """complete() + parse_json(), asking once more if the reply is not valid JSON."""
    try:
        return parse_json(complete(prompt, opts, schema=schema, name=name))
    except LLMError as first:
        if "failed after retries" in str(first):
            raise
        retry = prompt + "\n\nYour previous reply was not valid JSON. Reply again with only valid JSON."
        return parse_json(complete(retry, opts, schema=schema, name=name))
