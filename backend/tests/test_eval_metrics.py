import sys

from app.config import ROOT

sys.path.insert(0, str(ROOT / "eval"))
from metrics import claim_faithfulness, deadline_matches, pairwise_outcome  # noqa: E402

from app.llm.client import parse_json  # noqa: E402


def test_deadline_matches_counts_each_gold_date_once():
    assert deadline_matches(["2026-10-21", "2026-10-28"], ["2026-10-21", "2026-10-21"]) == 1
    assert deadline_matches([], ["2026-10-21"]) == 0


def test_claim_faithfulness():
    claims = [{"supported": True}, {"supported": "true"}, {"supported": False}, {}]
    assert claim_faithfulness(claims) == (0.5, 2, 4)
    assert claim_faithfulness([]) == (1.0, 0, 0)  # only placeholders and pleasantries
    assert claim_faithfulness([{"claim": "Room is [room number]", "supported": False}]) == (1.0, 0, 0)


def test_pairwise_needs_agreement_in_both_orders():
    assert pairwise_outcome("A", "B") == "rag"      # RAG chosen in both positions
    assert pairwise_outcome("B", "A") == "no_rag"
    assert pairwise_outcome("A", "A") == "tie"      # judge just preferred position A
    assert pairwise_outcome("tie", "B") == "tie"


def test_parse_json_ignores_reasoning_block():
    assert parse_json('<think>maybe {"x": 0}?</think>{"winner": "A"}') == {"winner": "A"}
