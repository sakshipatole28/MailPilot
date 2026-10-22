"""Evaluate MailPilot on the labeled data in data/. Writes CSVs and results/summary.md.

Every number in the README must come from here.

    cd backend
    .venv/bin/python ../eval/run_eval.py                       # retrieval + keyword baseline only
    .venv/bin/python ../eval/run_eval.py \
        --models groq/openai/gpt-oss-120b groq/openai/gpt-oss-20b groq/qwen/qwen3.8-27b \
        --draft-model groq/openai/gpt-oss-120b \
        --judges groq/qwen/qwen3.8-27b groq/openai/gpt-oss-20b

Draft quality is judged automatically, following published LLM-as-judge practice:
- claim-level faithfulness: the judge lists the draft's atomic claims and marks each as supported
  or not by the mail + context (RAGAS, Es et al. 2024; FActScore, Min et al. 2023)
- a rubric helpfulness score with written criteria per level (G-Eval, Liu et al. 2023)
- the primary judge comes from a different model family than the draft writer, because judges
  favor their own generations (Panickssery et al. 2024)
- pairwise RAG vs no-RAG, judged in both orders; a win must survive the swap (Zheng et al. 2023)
- a second judge, reporting agreement between judges as a check on the first

LLM responses are cached in SQLite, so an interrupted run resumes for free.
"""
import argparse
import csv
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "eval"))

from scipy.stats import spearmanr  # noqa: E402
from sklearn.metrics import accuracy_score, f1_score  # noqa: E402

from app import db  # noqa: E402
from app.config import DEFAULT_CATEGORIES, settings  # noqa: E402
from app.deps import get_retriever  # noqa: E402
from app.llm.classifier import keyword_classify, llm_classify  # noqa: E402
from app.llm.client import LLMError, complete_json, render_prompt  # noqa: E402
from app.llm.deadlines import extract_deadlines  # noqa: E402
from app.llm.generator import draft_reply, format_context  # noqa: E402
from app.mail_sources.file_source import FileMailSource  # noqa: E402
from app.models import LLMOptions  # noqa: E402
from metrics import claim_faithfulness, deadline_matches, pairwise_outcome  # noqa: E402

RESULTS = ROOT / "results"
KS = (1, 3, 5)


def write_csv(name: str, rows: list[dict]) -> None:
    if not rows:
        return
    with open(RESULTS / name, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def md_table(rows: list[dict]) -> str:
    if not rows:
        return "_no rows_\n"
    keys = list(rows[0].keys())
    lines = ["| " + " | ".join(keys) + " |", "|" + "---|" * len(keys)]
    lines += ["| " + " | ".join(str(r[k]) for k in keys) + " |" for r in rows]
    return "\n".join(lines) + "\n"


def mean(values) -> float | str:
    values = list(values)
    return round(statistics.mean(values), 3) if values else "n/a"


def load_data():
    labels = {r["id"]: r["label"] for r in json.loads((ROOT / "data/sample_mails.json").read_text())}
    mails = FileMailSource(ROOT / "data/sample_mails.json").fetch()
    return mails, labels


def call(fn, pause):
    """Run one LLM-backed call; return None (and print why) if it fails after retries."""
    try:
        result = fn()
        time.sleep(pause)
        return result
    except LLMError as e:
        print(f"    failed: {e}")
        return None


# ---------------- retrieval ----------------

def eval_retrieval(query_file: str) -> list[dict]:
    """Doc-level recall@k: share of a query's relevant files found in the top-k chunks."""
    queries = json.loads((ROOT / "data" / query_file).read_text())
    retriever = get_retriever()
    rows = []
    for mode in ("hybrid", "vector", "bm25"):
        recalls = {k: [] for k in KS}
        rr = []
        for q in queries:
            hits = [h.source for h in retriever.search(q["query"], k=max(KS), mode=mode)]
            relevant = set(q["relevant"])
            for k in KS:
                recalls[k].append(len(relevant & set(hits[:k])) / len(relevant))
            first = next((i for i, s in enumerate(hits, 1) if s in relevant), None)
            rr.append(1 / first if first else 0.0)
        row = {"query_set": query_file.removesuffix(".json"), "mode": mode, "queries": len(queries)}
        row.update({f"recall@{k}": mean(recalls[k]) for k in KS})
        row["mrr"] = mean(rr)
        rows.append(row)
        print(f"  {row}")
    return rows


# ---------------- classification ----------------

def eval_classification(mails, labels, models, pause) -> list[dict]:
    rows = []
    for name in ["keywords"] + models:
        y_true, y_pred, reply_true, reply_pred, failed = [], [], [], [], 0
        for mail in mails:
            if name == "keywords":
                result = keyword_classify(mail, DEFAULT_CATEGORIES)
            else:
                result = call(lambda: llm_classify(mail, LLMOptions(model=name),
                                                   DEFAULT_CATEGORIES), pause)
            if result is None:
                failed += 1
                continue
            y_true.append(labels[mail.id]["category"])
            y_pred.append(result.category)
            reply_true.append(labels[mail.id]["needs_reply"])
            reply_pred.append(result.needs_reply)
        rows.append({
            "model": name,
            "mails": len(y_pred),
            "accuracy": round(accuracy_score(y_true, y_pred), 3) if y_pred else "n/a",
            "macro_f1": round(f1_score(y_true, y_pred, labels=DEFAULT_CATEGORIES,
                                       average="macro", zero_division=0), 3) if y_pred else "n/a",
            "needs_reply_acc": round(accuracy_score(reply_true, reply_pred), 3) if y_pred else "n/a",
            "failed_calls": failed,
        })
        print(f"  {rows[-1]}")
    return rows


# ---------------- deadlines ----------------

def eval_deadlines(mails, labels, models, pause) -> list[dict]:
    """A predicted deadline is correct if its date matches a gold date of the same mail."""
    rows = []
    for name in models:
        tp = n_pred = n_gold = failed = done = 0
        for mail in mails:
            predicted = call(lambda: extract_deadlines(mail, LLMOptions(model=name)), pause)
            if predicted is None:
                failed += 1
                continue
            done += 1
            gold = [d["due_date"] for d in labels[mail.id]["deadlines"]]
            pred = [d.due_iso[:10] for d in predicted]
            tp += deadline_matches(gold, pred)
            n_pred += len(pred)
            n_gold += len(gold)
        p = tp / n_pred if n_pred else 0.0
        r = tp / n_gold if n_gold else 0.0
        rows.append({"model": name, "mails": done, "gold": n_gold, "predicted": n_pred,
                     "correct": tp, "precision": round(p, 3), "recall": round(r, 3),
                     "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0,
                     "failed_calls": failed})
        print(f"  {rows[-1]}")
    return rows


# ---------------- reply drafts ----------------

def judge_draft(draft: str, mail, chunks, judge_model: str) -> dict:
    prompt = render_prompt("judge", context=format_context(chunks), subject=mail.subject,
                           body=mail.body, draft=draft)
    data = complete_json(prompt, LLMOptions(model=judge_model))
    claims = [c for c in data.get("claims", [])
              if isinstance(c, dict) and "[" not in str(c.get("claim", ""))]
    faithfulness, supported, total = claim_faithfulness(claims)
    unsupported = [c.get("claim", "") for c in claims
                   if c.get("supported") not in (True, "true", "True")]
    return {"faithfulness": round(faithfulness, 3), "claims": total,
            "unsupported_claims": total - supported,
            "helpfulness": int(data.get("helpfulness", 0)),
            "unsupported": " | ".join(unsupported)[:500],
            "missing": str(data.get("missing", ""))[:300]}


def judge_pair(rag: str, no_rag: str, mail, chunks, judge_model: str) -> str:
    def ask(a: str, b: str) -> str:
        prompt = render_prompt("pairwise", context=format_context(chunks), subject=mail.subject,
                               body=mail.body, draft_a=a, draft_b=b)
        return str(complete_json(prompt, LLMOptions(model=judge_model)).get("winner", "tie"))

    return pairwise_outcome(ask(rag, no_rag), ask(no_rag, rag))


def eval_drafts(mails, labels, draft_model, judges, pause, second_judge_limit=None, limit=None):
    to_reply = [m for m in mails if labels[m.id]["needs_reply"]][:limit]
    retriever = get_retriever()
    opts = LLMOptions(model=draft_model)
    detail, pairs = [], []

    for n, mail in enumerate(to_reply, 1):
        print(f"  draft {n}/{len(to_reply)} {mail.id}")
        category = labels[mail.id]["category"]
        query = f"{mail.subject}\n{mail.body[:1000]}"
        chunks = retriever.search(query, k=settings.top_k, category=category, contact=mail.sender)
        style = retriever.search(query, k=2, contact=mail.sender, doc_type="reply")
        drafts = {
            "rag": call(lambda: draft_reply(mail, chunks, style, settings.tone, settings.user_name,
                                            "", opts), pause),
            "no_rag": call(lambda: draft_reply(mail, [], [], settings.tone, settings.user_name,
                                               "", opts), pause),
        }
        # Judges see the same notes for both conditions: a no-RAG draft is not punished for
        # lacking facts, only for inventing them.
        for cond, email in drafts.items():
            if email is None:
                continue
            for i, judge in enumerate(judges):
                if i > 0 and second_judge_limit is not None and n > second_judge_limit:
                    continue
                grade = call(lambda: judge_draft(email.body, mail, chunks, judge), pause)
                if grade is None:
                    continue
                detail.append({"mail_id": mail.id, "category": category, "condition": cond,
                               "judge": judge, **grade,
                               "guardrail_flags": len(email.issues),
                               "placeholders": email.body.count("["),
                               "sources": ";".join(c.source for c in (chunks if cond == "rag" else [])),
                               "draft": email.body})
        if judges and drafts["rag"] and drafts["no_rag"]:
            outcome = call(lambda: judge_pair(drafts["rag"].body, drafts["no_rag"].body, mail,
                                              chunks, judges[0]), pause)
            if outcome:
                pairs.append({"mail_id": mail.id, "judge": judges[0], "outcome": outcome})

    summary = []
    for judge in judges:
        for cond in ("rag", "no_rag"):
            rows = [d for d in detail if d["judge"] == judge and d["condition"] == cond]
            summary.append({
                "judge": judge, "condition": cond, "drafts": len(rows),
                "faithfulness": mean(r["faithfulness"] for r in rows),
                "unsupported_claims_per_draft": mean(r["unsupported_claims"] for r in rows),
                "helpfulness_1to5": mean(r["helpfulness"] for r in rows),
                "guardrail_flags_per_draft": mean(r["guardrail_flags"] for r in rows),
            })
            print(f"  {summary[-1]}")

    pairwise = []
    if pairs:
        counts = {k: sum(p["outcome"] == k for p in pairs) for k in ("rag", "no_rag", "tie")}
        pairwise.append({"judge": judges[0], "mails": len(pairs), "rag_wins": counts["rag"],
                         "no_rag_wins": counts["no_rag"], "ties_or_order_flips": counts["tie"]})
        print(f"  {pairwise[-1]}")

    agreement = []
    if len(judges) >= 2:
        a, b = judges[0], judges[1]
        key = lambda d: (d["mail_id"], d["condition"])  # noqa: E731
        first = {key(d): d for d in detail if d["judge"] == a}
        second = {key(d): d for d in detail if d["judge"] == b}
        shared = sorted(set(first) & set(second))
        for metric in ("faithfulness", "helpfulness"):
            x = [first[k][metric] for k in shared]
            y = [second[k][metric] for k in shared]
            rho = spearmanr(x, y).statistic if len(shared) > 2 and len(set(x)) > 1 and len(set(y)) > 1 else float("nan")
            agreement.append({"metric": metric, "judge_a": a, "judge_b": b, "drafts": len(shared),
                              "spearman": round(float(rho), 3),
                              "mean_abs_diff": mean(abs(i - j) for i, j in zip(x, y))})
            print(f"  {agreement[-1]}")
    return summary, detail, pairs, pairwise, agreement


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="*", default=[], help="models for classification + deadlines")
    parser.add_argument("--deadline-models", nargs="*", default=None,
                        help="models for deadline extraction (default: --models)")
    parser.add_argument("--draft-limit", type=int, default=None,
                        help="evaluate drafts for only the first N needs-reply mails")
    parser.add_argument("--second-judge-limit", type=int, default=None,
                        help="grade only the first N mails with the second judge (saves quota)")
    parser.add_argument("--draft-model", default=None, help="writes the drafts (default: first --models)")
    parser.add_argument("--judges", nargs="*", default=[], help="judge models; the first is primary")
    parser.add_argument("--sleep", type=float, default=0.0, help="seconds between LLM calls")
    parser.add_argument("--retries", type=int, default=8, help="retries on rate limits")
    parser.add_argument("--skip-drafts", action="store_true")
    args = parser.parse_args()

    settings.llm_retries = args.retries
    RESULTS.mkdir(exist_ok=True)
    db.init_db()
    mails, labels = load_data()
    print(f"{len(mails)} labeled mails, models: {args.models or 'none (baseline only)'}")
    sections = []

    print("retrieval")
    retrieval = eval_retrieval("retrieval_eval.json") + eval_retrieval("retrieval_eval_paraphrased.json")
    write_csv("retrieval.csv", retrieval)
    sections.append(("Retrieval: hybrid vs vector vs BM25 (doc-level recall@k, MRR)", retrieval))

    print("classification")
    classification = eval_classification(mails, labels, args.models, args.sleep)
    write_csv("classification.csv", classification)
    sections.append(("Classification (5 categories)", classification))

    if args.models:
        print("deadlines")
        deadline_models = args.models if args.deadline_models is None else args.deadline_models
        deadlines = eval_deadlines(mails, labels, deadline_models, args.sleep)
        write_csv("deadlines.csv", deadlines)
        sections.append(("Deadline extraction (date match)", deadlines))

    draft_model = args.draft_model or (args.models[0] if args.models else None)
    if draft_model and args.judges and not args.skip_drafts:
        print(f"drafts: writer {draft_model}, judges {args.judges}")
        summary, detail, pairs, pairwise, agreement = eval_drafts(
            mails, labels, draft_model, args.judges, args.sleep, args.second_judge_limit,
            args.draft_limit)
        write_csv("drafts.csv", summary)
        write_csv("drafts_detail.csv", detail)
        write_csv("drafts_pairwise.csv", pairs)
        write_csv("judge_agreement.csv", agreement)
        sections.append((f"Reply drafts: RAG vs no RAG, written by {draft_model}", summary))
        sections.append(("Reply drafts: pairwise preference (both orders must agree)", pairwise))
        sections.append(("Judge agreement (Spearman, per draft)", agreement))

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    text = [f"# MailPilot eval results\n\nGenerated by `eval/run_eval.py` on {stamp}. "
            f"Dataset: {len(mails)} labeled mails in `data/sample_mails.json`.\n"]
    for title, rows in sections:
        text.append(f"## {title}\n\n{md_table(rows)}")
    (RESULTS / "summary.md").write_text("\n".join(text), encoding="utf-8")
    print(f"wrote {RESULTS / 'summary.md'}")


if __name__ == "__main__":
    main()
