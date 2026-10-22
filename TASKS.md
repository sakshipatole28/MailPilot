# Tasks

## Done
- [x] Backend: config, SQLite, models, redacting logger
- [x] Mail sources: FileMailSource (JSON, mbox), GmailMailSource (OAuth, read-only)
- [x] LLM client (LiteLLM) with retry and SQLite response cache; per-request model and key
- [x] Classifier (LLM + keyword fallback/baseline), deadline extractor with evidence check
- [x] Reply and compose generator with regex guardrails
- [x] RAG: chunker with front matter, Chroma + bge-small, BM25, RRF, category/contact/doc-type filters, optional rerank
- [x] API: mail, classify, deadlines, draft, feedback, compose, rag ingest, settings
- [x] 61 labeled sample mails (23 need a reply), 15-file context corpus
- [x] Two labeled retrieval query sets (original wording + paraphrased)
- [x] Backend tests and extension tests, run in GitHub Actions CI
- [x] Extension: popup with 5 tabs, background alarms (24 h / 2 h), badge for items due today
- [x] Eval on three Groq models; draft quality judged with claim-level faithfulness, rubric helpfulness, swapped-order pairwise preference and two judges
- [x] README, DECISIONS, architecture diagram, demo GIF from the real app

## Open
- [ ] Gmail: test with a real account (needs `secrets/credentials.json` from Google Cloud)
- [ ] Stretch: `gmail.compose` scope to save drafts directly into Gmail
- [ ] Stretch: a small human-rated subset to calibrate the LLM judges
