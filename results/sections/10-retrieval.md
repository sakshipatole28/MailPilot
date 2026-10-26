## Retrieval: hybrid vs vector vs BM25 (doc-level recall@k, MRR)

| query_set | mode | queries | recall@1 | recall@3 | recall@5 | mrr |
|---|---|---|---|---|---|---|
| retrieval_eval | hybrid | 18 | 0.722 | 0.889 | 0.944 | 0.847 |
| retrieval_eval | vector | 18 | 0.583 | 0.75 | 0.833 | 0.708 |
| retrieval_eval | bm25 | 18 | 0.806 | 0.972 | 0.972 | 0.944 |
| retrieval_eval_paraphrased | hybrid | 18 | 0.5 | 0.694 | 0.833 | 0.676 |
| retrieval_eval_paraphrased | vector | 18 | 0.472 | 0.556 | 0.694 | 0.588 |
| retrieval_eval_paraphrased | bm25 | 18 | 0.306 | 0.528 | 0.694 | 0.502 |

_Run: 2026-10-26_
