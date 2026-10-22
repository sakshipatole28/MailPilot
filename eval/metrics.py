"""Pure scoring helpers used by run_eval.py (unit tested in backend/tests/test_eval_metrics.py)."""
from collections import Counter


def deadline_matches(gold_dates: list[str], predicted_dates: list[str]) -> int:
    """Number of predicted dates (YYYY-MM-DD) that match a gold date; each gold date matches once."""
    return sum((Counter(gold_dates) & Counter(predicted_dates)).values())


def claim_faithfulness(claims: list[dict]) -> tuple[float, int, int]:
    """RAGAS-style faithfulness: supported claims / all claims. A draft with no factual claims
    (only placeholders and pleasantries) cannot be unfaithful, so it scores 1.0."""
    # Judges sometimes list "[room number]"-style placeholders as claims, against the
    # instructions; a placeholder is the desired behavior, so it is not scored.
    claims = [c for c in claims if "[" not in str(c.get("claim", ""))]
    total = len(claims)
    supported = sum(1 for c in claims if c.get("supported") in (True, "true", "True"))
    return (supported / total if total else 1.0), supported, total


def pairwise_outcome(first: str, second: str) -> str:
    """Combine two pairwise judgments of RAG vs no-RAG made in swapped order.

    first:  winner when RAG was shown as A and no-RAG as B
    second: winner when no-RAG was shown as A and RAG as B
    A side only wins if the judge picks it in both orders (Zheng et al., 2023);
    a judgment that flips with the order counts as a tie.
    """
    def as_rag(winner: str, rag_label: str) -> str:
        winner = winner.strip().upper()
        if winner not in ("A", "B"):
            return "tie"
        return "rag" if winner == rag_label else "no_rag"

    a, b = as_rag(first, "A"), as_rag(second, "B")
    return a if a == b else "tie"
