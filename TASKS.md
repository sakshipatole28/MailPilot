# Tasks

## Done
- [x] Backend: FastAPI, SQLite with automatic migrations, redacting logger
- [x] Mail sources: Gmail (OAuth, read-only, security headers + labels) and file (JSON, mbox)
- [x] LiteLLM client: retry/backoff honoring provider hints, JSON repair, strict structured outputs with fallback, cache, metrics
- [x] Triage in one call: category, intents, importance, summary, tasks, phishing opinion; validated
- [x] Configurable categories (general / student presets, plain-language descriptions); corrections as few-shot examples
- [x] Priority score 0-100 with reasons
- [x] Phishing signals + LLM opinion; prompt-injection defenses (spotlighting, detector, notes withheld)
- [x] Background worker: triage + indexing after sync
- [x] LangGraph: self-correcting drafts, agentic Ask your inbox
- [x] OpenTelemetry tracing (/traces, optional OTLP), /metrics
- [x] Extension: Today brief, split views, Tasks with .ics export, Draft with risk warning + quick replies, Ask, category editor, auto-sync
- [x] Eval: classification, deadlines, triage, retrieval (two query sets), drafts (claim-level faithfulness, cross-family judges), phishing P/R, injection attack success rate, self-correction
- [x] CI on GitHub Actions; README, DECISIONS, architecture diagram, demo

## Next
- [ ] Held-out labeled set (the deadline prompt was refined on the eval set)
- [ ] Gmail draft creation (`gmail.compose`) behind an explicit button
- [ ] Thread view: triage whole threads, not single messages
- [ ] Follow-up tracking ("waiting on" for mail you sent)
- [ ] Multi-user deployment: Postgres, task queue, authentication
