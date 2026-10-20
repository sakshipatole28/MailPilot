# Tasks

## Done
- [x] Backend: config, SQLite, models, redacting logger
- [x] Mail sources: FileMailSource (JSON, mbox), GmailMailSource (OAuth, read-only)
- [x] LLM client (LiteLLM) with retry and SQLite response cache; per-request model and key
- [x] Classifier (LLM + keyword fallback/baseline), deadline extractor with evidence check
- [x] Reply and compose generator with regex guardrails
- [x] RAG: chunker with front matter, Chroma + bge-small, BM25, RRF, category/contact/doc-type filters, optional rerank
- [x] API: mail, classify, deadlines, draft, feedback, compose, rag ingest, settings
- [x] 55 labeled sample mails, 15-file context corpus, 18 labeled retrieval queries
- [x] Backend tests (40) and extension tests (4)
- [x] Extension: popup with 5 tabs, background alarms (24 h / 2 h), badge for items due today
- [x] Eval script; retrieval and keyword-baseline results in results/
- [x] Dockerfile + docker-compose.yml (config validated)
- [x] README, DECISIONS, architecture diagram, UI screenshots

## Open
- [ ] Run `eval/run_eval.py --models ...` with a Gemini/Groq key (or Ollama) and copy the LLM rows into the README
- [ ] Fill in `results/manual_ratings.csv` (manual 1-5 on a subset of drafts)
- [ ] Record a demo GIF that includes a generated draft (needs a model)
- [ ] Build and run the Docker image once (`docker compose up --build`); it was not built on the dev machine because of disk space
- [ ] Paraphrased retrieval queries to compare hybrid vs BM25 fairly
- [ ] Stretch: `gmail.compose` scope to save drafts directly into Gmail
- [ ] Add 5-10 more needs-reply mails so the draft eval reaches the planned 20-30
