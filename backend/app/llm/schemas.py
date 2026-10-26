"""JSON schemas for structured outputs.

When the provider supports it (Groq, OpenAI, Gemini ... per LiteLLM), the model is constrained
to these schemas, so a reply cannot be malformed JSON or use a category that does not exist.
Strict mode needs every property listed in "required" and additionalProperties false. Prompts
still describe the format too, so providers without schema support work the same way.
"""
from app.llm.taxonomy import INTENTS
from app.models import Category


def obj(properties: dict) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False}


STRING = {"type": "string"}
STRINGS = {"type": "array", "items": STRING}


def triage(categories: list[Category]) -> dict:
    return obj({
        "category": {"type": "string", "enum": [c.name for c in categories]},
        "intents": {"type": "array", "items": {"type": "string", "enum": list(INTENTS)}},
        "importance": {"type": "integer"},
        "summary": STRING,
        "action_items": {"type": "array", "items": obj({
            "task": STRING, "due_iso": {"type": ["string", "null"]}, "evidence": STRING})},
        "suspicious": {"type": "boolean"},
        "suspicious_reasons": STRINGS,
    })


REPLY = obj({"subject": STRING, "body": STRING, "quick_replies": STRINGS})
COMPOSE = obj({"subject": STRING, "body": STRING})
REVISE = obj({"subject": STRING, "body": STRING})
ASK_STEP = obj({"action": {"type": "string", "enum": ["search", "answer"]},
                "query": STRING, "answer": STRING, "mail_ids": STRINGS})
JUDGE = obj({"claims": {"type": "array", "items": obj({"claim": STRING, "supported": {"type": "boolean"}})},
             "helpfulness": {"type": "integer"}, "missing": STRING})
PAIRWISE = obj({"winner": {"type": "string", "enum": ["A", "B", "tie"]}, "reason": STRING})
