# Decisions

Short log of choices and why, so each can be defended in an interview.

1. **Plain `sqlite3`, no ORM.** Five small tables; raw SQL is easier to read and explain than SQLAlchemy models.
2. **LiteLLM for every provider.** One `completion()` call covers Gemini, Groq, Ollama, OpenAI and Anthropic. The model string (`groq/...`, `ollama/...`) picks the provider.
3. **Default model `groq/openai/gpt-oss-120b`.** The original plan named `gemini-2.0-flash` and `llama-3.3-70b-versatile`, but both have been retired by their providers. gpt-oss-120b is on Groq's free tier. It is a single env var (`MODEL`), so any LiteLLM model works.
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
15. **No Docker.** The backend is one `uvicorn` process with a virtualenv. A Dockerfile added a 2 GB image (torch + Chroma) without making setup simpler for a Chrome-extension user, who still has to build and load the extension. CI covers what Docker would prove (a clean install runs).
16. **Automated draft evaluation instead of manual ratings.** Human ratings by the author would be biased and could not be reproduced. The eval follows published LLM-as-judge practice:
    - claim-level faithfulness: the judge lists every atomic claim and marks it supported or not by the mail + notes (RAGAS, Es et al. 2024; FActScore, Min et al. 2023)
    - a rubric helpfulness score with a written description for each level (G-Eval, Liu et al. 2023)
    - a judge from a different model family than the writer, because judges favor their own outputs (Panickssery et al. 2024)
    - pairwise RAG vs no-RAG, asked in both orders, where a win only counts if it survives the swap (position bias, Zheng et al. 2023)
    - a second judge, with agreement reported as a check on the first
17. **Two retrieval query sets.** The first set was written with the notes' own vocabulary, which favors BM25. A paraphrased set with low word overlap tests whether the vector half earns its place.
