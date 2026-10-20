"""Reply drafts and new emails: prompt -> LLM -> guardrails."""
from app.llm.client import LLMError, complete, parse_json, render_prompt
from app.llm.guardrails import check_draft
from app.models import GeneratedEmail, LLMOptions, Mail, SourceChunk


def format_context(chunks: list[SourceChunk]) -> str:
    if not chunks:
        return "(none)"
    return "\n\n".join(f"[{i}] ({c.title}) {c.text}" for i, c in enumerate(chunks, 1))


def _subject_and_body(raw: str, default_subject: str) -> tuple[str, str]:
    try:
        data = parse_json(raw)
        return str(data.get("subject") or default_subject), str(data.get("body", "")).strip()
    except LLMError:
        return default_subject, raw.strip()  # model ignored the JSON format: keep its text


def _finish(subject: str, body: str, source_text: str, chunks, model: str) -> GeneratedEmail:
    checked_subject = check_draft(subject, source_text)
    checked_body = check_draft(body, source_text)
    return GeneratedEmail(
        subject=checked_subject.text,
        body=checked_body.text,
        sources=chunks,
        issues=checked_subject.issues + checked_body.issues,
        model=model,
    )


def draft_reply(mail: Mail, chunks: list[SourceChunk], style_examples: list[SourceChunk],
                tone: str, user_name: str, instruction: str, opts: LLMOptions) -> GeneratedEmail:
    prompt = render_prompt(
        "reply",
        user_name=user_name,
        tone=tone,
        instruction=f"- Extra instruction from {user_name}: {instruction}\n" if instruction else "",
        style_examples="\n---\n".join(c.text for c in style_examples) or "(none)",
        context=format_context(chunks),
        sender=f"{mail.sender_name} <{mail.sender}>",
        subject=mail.subject,
        received_at=mail.received_at.strftime("%A %d %B %Y"),
        body=mail.body[:4000],
    )
    subject, body = _subject_and_body(complete(prompt, opts), f"Re: {mail.subject}")
    # Style examples are deliberately not part of the source text: they must not license facts.
    source_text = "\n".join([mail.sender, mail.sender_name, mail.subject, mail.body,
                             instruction, user_name] + [c.text for c in chunks])
    return _finish(subject, body, source_text, chunks, opts.model)


def compose_email(instruction: str, chunks: list[SourceChunk], tone: str, user_name: str,
                  opts: LLMOptions) -> GeneratedEmail:
    prompt = render_prompt(
        "compose", user_name=user_name, tone=tone, context=format_context(chunks),
        instruction=instruction,
    )
    subject, body = _subject_and_body(complete(prompt, opts), "")
    source_text = "\n".join([instruction, user_name] + [c.text for c in chunks])
    return _finish(subject, body, source_text, chunks, opts.model)
