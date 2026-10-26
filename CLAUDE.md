# MailPilot: notes for Claude

Chrome MV3 popup + local FastAPI backend: background triage of mail (category, intents, priority, tasks, phishing), self-correcting RAG drafts, an Ask-your-inbox agent, compose. Never sends mail.

## Hard rules
- Never auto-send email. Only return text or create drafts.
- Never invent dates, links, names or commitments in drafts; missing info becomes a `[placeholder]`. `app/llm/guardrails.py` enforces this.
- No secrets in git. Keys live in `.env` (backend) or `chrome.storage.local` (user keys, sent per request as `X-Api-Key`).
- Never log mail bodies. Logs go through `app/redact.py` (emails, phones, names after greetings/sign-offs).
- Every module has a test. Keep code simple enough to explain in an interview.
- README numbers must come from `eval/run_eval.py` output in `results/`.

## Layout
- `backend/app/`: `api/` routers, `agents/` (LangGraph: draft_graph, ask_graph), `llm/` (client, triage, taxonomy, priority, security, schemas, generator, guardrails, deadlines, classifier), `rag/` (chunker, store, retriever, ingest), `mail_sources/` (gmail, file), `jobs.py` (background worker), `tracing.py` (OpenTelemetry), `prompts/*.txt`
- `extension/`: Vite + React + CRXJS; `src/background` (auto-sync, alarms, badge), `src/popup` (Inbox, Tasks, Draft, Ask, Compose, Settings), `src/shared` (api client, inbox views, reminders, storage)
- `data/sample_mails.json`: labeled mails (`label.category`, `label.needs_reply`, `label.deadlines`)
- `data/context/`: RAG corpus (markdown with `---` front matter: type, category, contact)
- `eval/`: `run_eval.py` writes CSVs and `results/sections/*.md`; `results/summary.md` joins the sections
- Tests force the sample inbox and a temp DB (see `tests/conftest.py`); never call real Gmail or a real LLM from tests

## Commands
- Backend dev: `cd backend && .venv/bin/uvicorn app.main:app --reload`
- Tests: `cd backend && .venv/bin/pytest -q`
- Extension: `cd extension && npm run build` then load `extension/dist` unpacked
- Eval: `cd backend && .venv/bin/python ../eval/run_eval.py --models groq/openai/gpt-oss-120b --judges groq/qwen/qwen3.8-27b` (see the docstring for the full run)
