## Input tokens per mail: separate prompts vs one triage call

Counted with the o200k tokenizer on the rendered prompts; output and reasoning tokens excluded.

| design | llm_calls_per_mail | input_tokens_per_mail |
|---|---|---|
| separate classify + deadline prompts | 2 | 1019 |
| one triage prompt (also: summary, intents, priority, phishing) | 1 | 1119 |

_Run: 2026-10-27_
