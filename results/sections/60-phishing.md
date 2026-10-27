## Phishing detection

20 hand-written mails (10 phishing, 10 legitimate look-alikes such as real security alerts, bank reminders and newsletters with short links).

| detector | precision | recall | f1 | false_positives |
|---|---|---|---|---|
| header/link rules (medium or high) | 1.0 | 0.8 | 0.889 | 0 |
| LLM only (groq/openai/gpt-oss-20b) | 1.0 | 1.0 | 1.0 | 0 |
| combined score = high (shipped) | 1.0 | 1.0 | 1.0 | 0 |

_Run: 2026-10-27_
