# MailPilot: notes for Claude

Chrome MV3 popup + FastAPI backend that categorizes mail, extracts deadlines, drafts replies (RAG) and composes new mail.

## Hard rules
- Never auto-send email. Only return text or create drafts.
- Never invent dates, links, names or commitments in drafts; missing info becomes a `[placeholder]`. `app/llm/guardrails.py` enforces this.
- No secrets in git. Keys live in `.env` (backend) or `chrome.storage.local` (user keys, sent per request as `X-Api-Key`).
- Never log mail bodies. Logs go through `app/redact.py` (emails, phones, names after greetings/sign-offs).
- Every module has a test. Keep code simple enough to explain in an interview.
- README numbers must come from `eval/run_eval.py` output in `results/`.

## Layout
- `backend/app/`: `api/` routers, `mail_sources/` (file, gmail), `llm/` (client, classifier, deadlines, generator, guardrails), `rag/` (chunker, store, retriever, ingest), `prompts/*.txt`
- `extension/`: Vite + React + CRXJS; `src/background` (alarms, badge), `src/popup` (5 tabs), `src/shared` (api client, types, storage)
- `data/sample_mails.json`: labeled mails (`label.category`, `label.needs_reply`, `label.deadlines`)
- `data/context/`: RAG corpus (markdown with `---` front matter: type, category, contact)
- `eval/`: `run_eval.py` writes CSV + markdown to `results/`

## Commands
- Backend dev: `cd backend && .venv/bin/uvicorn app.main:app --reload`
- Tests: `cd backend && .venv/bin/pytest -q`
- Extension: `cd extension && npm run build` then load `extension/dist` unpacked
- Eval: `cd backend && .venv/bin/python ../eval/run_eval.py --models gemini/gemini-2.5-flash`
