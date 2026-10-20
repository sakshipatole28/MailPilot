# Decisions

Short log of choices and why, so each can be defended in an interview.

1. **Plain `sqlite3`, no ORM.** Five small tables; raw SQL is easier to read and explain than SQLAlchemy models.
2. **LiteLLM for every provider.** One `completion()` call covers Gemini, Groq, Ollama, OpenAI and Anthropic. The model string (`groq/...`, `ollama/...`) picks the provider.
3. **Default model `gemini/gemini-2.5-flash`** instead of `gemini-2.0-flash` from the original plan, because Google is retiring 2.0 Flash. It is a single env var (`MODEL`), so either works.
4. **Prompt-only JSON, not provider JSON mode.** Not every provider supports `response_format` in the same way, so prompts ask for JSON and `parse_json()` pulls the first `{...}` block out of the reply. Fewer provider-specific branches.
5. **Response cache in SQLite** keyed by `sha256(model + messages)`. Re-running the eval or re-opening a draft costs zero API calls, which matters on free-tier rate limits. Retries use exponential backoff on rate-limit, timeout and connection errors only.
6. **Keyword classifier runs on sync, the LLM runs on demand.** Classifying 50 mails with an LLM on every sync would hit free-tier limits (Gemini free tier is about 10-15 requests per minute). Sync gives every mail an instant keyword label marked `classified_by="keywords"`. The popup's "Classify with AI" button and the draft flow upgrade it to `classified_by="llm"`. The keyword classifier also serves as the baseline row in the eval.
7. **Deadline evidence check.** The extractor must quote the words that state the date (`evidence`). A deadline whose evidence is not found in the mail is dropped. This cheaply removes hallucinated dates.
8. **Guardrails are regex checks, not a second LLM call.** Dates, times, weekdays, URLs, emails and phone numbers in a draft must appear in the mail, the retrieved context or the user's instruction. Anything else becomes `[confirm: ...]` and is reported as an issue. This is deterministic, free and testable. It cannot catch every invented fact; see README limitations.
9. **Hybrid retrieval = Chroma (bge-small) + BM25, merged with reciprocal rank fusion (k=60).** RRF uses ranks only, so the two score scales never need calibrating. The cross-encoder rerank is optional (`RERANK=true`) to keep the default install light.
10. **Contact filter for privacy.** Context chunks can carry a `contact`. When drafting for sender X, chunks tied to a different contact are excluded, so one person's thread never leaks into a reply to someone else.
11. **Per-request model and key via headers** (`X-Model`, `X-Api-Key`). User-supplied keys stay in `chrome.storage.local` and are never stored by the backend or written to logs.
12. **Popup loops over mails for batch actions** instead of a batch endpoint, so the UI can show progress and one rate-limited mail does not fail the whole batch.
13. **Extension built with Vite + CRXJS**, the lighter of the two options in the plan, with no framework conventions to learn.
14. **Relevance in the retrieval eval is labeled per document, not per chunk.** Chunk ids change when chunking parameters change; file names do not.
