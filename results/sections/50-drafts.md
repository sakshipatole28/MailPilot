## Reply drafts: RAG vs no RAG, written by groq/openai/gpt-oss-120b (reply prompt v1)

_Measured with reply prompt v1 (before spotlighting and quick replies were added), 2026-10-22. Not re-run since, to stay within the free-tier daily token limit._

| judge | condition | drafts | faithfulness | unsupported_claims_per_draft | helpfulness_1to5 | guardrail_flags_per_draft |
|---|---|---|---|---|---|---|
| groq/qwen/qwen3.8-27b | rag | 22 | 0.823 | 0.773 | 4.136 | 0.364 |
| groq/qwen/qwen3.8-27b | no_rag | 23 | 0.691 | 1.13 | 3.565 | 0.087 |
| groq/openai/gpt-oss-20b | rag | 15 | 0.656 | 1.4 | 4.533 | 0.533 |
| groq/openai/gpt-oss-20b | no_rag | 13 | 0.66 | 1.308 | 4.385 | 0 |

_Run: 2026-10-22_
