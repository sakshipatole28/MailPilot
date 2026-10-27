"""Reply drafts and new emails: prompt -> LLM -> guardrails."""
from app.config import settings
from app.llm import schemas, security
from app.llm.client import LLMError, complete, parse_json, render_prompt
from app.llm.guardrails import check_draft
from app.models import GeneratedEmail, LLMOptions, Mail, SourceChunk


def format_context(chunks: list[SourceChunk]) -> str:
    if not chunks:
        return "(none)"
    return "\n\n".join(f"[{i}] ({c.title}) {c.text}" for i, c in enumerate(chunks, 1))


def _parse(raw: str, default_subject: str) -> tuple[str, str, list[str]]:
    """(subject, body, quick replies) from the model's JSON, tolerating a plain-text reply."""
    try:
        data = parse_json(raw)
    except LLMError:
        return default_subject, security.unmark(raw.strip()), []  # model ignored the format
    quick = [security.unmark(str(q)).strip() for q in data.get("quick_replies", []) if str(q).strip()]
    return (security.unmark(str(data.get("subject") or default_subject)),
            security.unmark(str(data.get("body", "")).strip()), quick[:3])


def _finish(subject: str, body: str, source_text: str, chunks, model: str,
            quick_replies: list[str] = (), link_source: str | None = None) -> GeneratedEmail:
    checked_subject = check_draft(subject, source_text, link_source)
    checked_body = check_draft(body, source_text, link_source)
    # A quick reply is dropped, not patched, if it states anything unsupported.
    safe_quick = [q for q in quick_replies if not check_draft(q, source_text, link_source).issues]
    return GeneratedEmail(
        subject=checked_subject.text,
        body=checked_body.text,
        sources=chunks,
        issues=checked_subject.issues + checked_body.issues,
        quick_replies=safe_quick,
        model=model,
    )


def reply_link_source(mail: Mail, chunks: list[SourceChunk], instruction: str) -> str:
    """Where a reply may take links and email addresses from: the user's notes and instruction,
    plus the sender's own address (replying "write to me at ..." is normal)."""
    return "\n".join([mail.sender, instruction] + [c.text for c in chunks])


def reply_source_text(mail: Mail, chunks: list[SourceChunk], instruction: str, user_name: str) -> str:
    """What a reply may state facts from. Style examples are deliberately excluded: they show
    how the user writes, they must not license facts."""
    return "\n".join([mail.sender, mail.sender_name, mail.subject, mail.body, instruction,
                      user_name] + [c.text for c in chunks])


def generate_reply(mail: Mail, chunks: list[SourceChunk], style_examples: list[SourceChunk],
                   tone: str, user_name: str, instruction: str, opts: LLMOptions,
                   spotlight_mode: str | None = None) -> tuple[str, str, list[str]]:
    """One reply-generation call: (subject, body, quick replies), not yet guardrail-checked."""
    body, note = security.spotlight(mail.body[:4000], spotlight_mode or settings.spotlight)
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
        untrusted_note=note,
        body=body,
    )
    return _parse(complete(prompt, opts, schema=schemas.REPLY, name="reply"), f"Re: {mail.subject}")


def revise_reply(mail: Mail, chunks: list[SourceChunk], subject: str, body: str,
                 problems: list[str], user_name: str, opts: LLMOptions,
                 spotlight_mode: str | None = None) -> tuple[str, str]:
    """Ask the model to fix the specific unsupported facts the guardrail found."""
    marked, note = security.spotlight(mail.body[:4000], spotlight_mode or settings.spotlight)
    prompt = render_prompt(
        "revise", user_name=user_name, context=format_context(chunks),
        problems="\n".join(f"- {p}" for p in problems), subject=subject, draft=body,
        sender=f"{mail.sender_name} <{mail.sender}>", mail_subject=mail.subject,
        untrusted_note=note, body=marked)
    new_subject, new_body, _ = _parse(complete(prompt, opts, schema=schemas.REVISE, name="revise"), subject)
    return new_subject, new_body


def draft_reply(mail: Mail, chunks: list[SourceChunk], style_examples: list[SourceChunk],
                tone: str, user_name: str, instruction: str, opts: LLMOptions,
                spotlight_mode: str | None = None) -> GeneratedEmail:
    """Single pass: generate, then guardrails. (The API uses the self-correcting graph in
    app/agents/draft_graph.py; this stays for the eval's defense comparisons.)"""
    subject, body, quick = generate_reply(mail, chunks, style_examples, tone, user_name,
                                          instruction, opts, spotlight_mode)
    source_text = reply_source_text(mail, chunks, instruction, user_name)
    return _finish(subject, body, source_text, chunks, opts.model, quick,
                   reply_link_source(mail, chunks, instruction))


def compose_email(instruction: str, chunks: list[SourceChunk], tone: str, user_name: str,
                  opts: LLMOptions) -> GeneratedEmail:
    prompt = render_prompt(
        "compose", user_name=user_name, tone=tone, context=format_context(chunks),
        instruction=instruction,
    )
    subject, body, _ = _parse(complete(prompt, opts, schema=schemas.COMPOSE, name="compose"), "")
    source_text = "\n".join([instruction, user_name] + [c.text for c in chunks])
    return _finish(subject, body, source_text, chunks, opts.model)
