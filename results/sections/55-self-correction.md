## Self-correcting drafts (LangGraph), written by groq/openai/gpt-oss-20b

Unsupported facts = dates, times, weekdays, links, emails, phone numbers or greeting names that neither the mail nor the notes contain (the guardrail's check). Single pass masks them with [confirm: ...]; the graph first asks the model to fix them (at most 2 rounds), then masks whatever is left.

| drafts | drafts_with_unsupported_facts_first_pass | revised | unsupported_facts_first_pass | left_after_revision | judge | faithfulness_single_pass | faithfulness_self_correcting | helpfulness_single_pass | helpfulness_self_correcting |
|---|---|---|---|---|---|---|---|---|---|
| 23 | 4 | 4 | 10 | 0 | groq/qwen/qwen3.8-27b | 0.861 | 0.839 | 4.261 | 4.043 |

_Run: 2026-10-27_
