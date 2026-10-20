"""Evaluate MailPilot on data/sample_mails.json and data/retrieval_eval.json.

Writes CSVs and results/summary.md. Every number in the README must come from here.

    cd backend
    .venv/bin/python ../eval/run_eval.py                                 # retrieval + keyword baseline
    .venv/bin/python ../eval/run_eval.py --models gemini/gemini-2.5-flash groq/llama-3.3-70b-versatile
    .venv/bin/python ../eval/run_eval.py --models ollama/qwen2.5:7b --skip-drafts

LLM responses are cached in SQLite, so re-runs are free. Use --sleep on free tiers.
"""
import argparse
import csv
import json
import statistics
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sklearn.metrics import accuracy_score, f1_score  # noqa: E402

from app import db  # noqa: E402
from app.config import DEFAULT_CATEGORIES, settings  # noqa: E402
from app.deps import get_retriever  # noqa: E402
from app.llm.classifier import keyword_classify, llm_classify  # noqa: E402
from app.llm.client import LLMError, complete, parse_json, render_prompt  # noqa: E402
from app.llm.deadlines import extract_deadlines  # noqa: E402
from app.llm.generator import draft_reply, format_context  # noqa: E402
from app.mail_sources.file_source import FileMailSource  # noqa: E402
from app.models import LLMOptions  # noqa: E402

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


def load_data():
    labels = {r["id"]: r["label"] for r in json.loads((ROOT / "data/sample_mails.json").read_text())}
    mails = FileMailSource(ROOT / "data/sample_mails.json").fetch()
    return mails, labels


# ---------------- classification ----------------

def eval_classification(mails, labels, models, pause) -> list[dict]:
    rows = []
    for name in ["keywords"] + models:
        y_true, y_pred, reply_true, reply_pred, failed = [], [], [], [], 0
        for mail in mails:
            try:
                if name == "keywords":
                    result = keyword_classify(mail, DEFAULT_CATEGORIES)
                else:
                    result = llm_classify(mail, LLMOptions(model=name), DEFAULT_CATEGORIES)
                    time.sleep(pause)
            except LLMError as e:
                failed += 1
                if failed == 1 and not y_pred:
                    print(f"  {name}: skipped ({e})")
                    break
                continue
            y_true.append(labels[mail.id]["category"])
            y_pred.append(result.category)
            reply_true.append(labels[mail.id]["needs_reply"])
            reply_pred.append(result.needs_reply)
        if not y_pred:
            rows.append({"model": name, "n": 0, "accuracy": "skipped", "macro_f1": "skipped",
                         "needs_reply_acc": "skipped", "failed_calls": failed})
            continue
        rows.append({
            "model": name,
            "n": len(y_pred),
            "accuracy": round(accuracy_score(y_true, y_pred), 3),
            "macro_f1": round(f1_score(y_true, y_pred, labels=DEFAULT_CATEGORIES,
                                       average="macro", zero_division=0), 3),
            "needs_reply_acc": round(accuracy_score(reply_true, reply_pred), 3),
            "failed_calls": failed,
        })
        print(f"  classification {name}: {rows[-1]}")
    return rows


# ---------------- deadlines ----------------

def eval_deadlines(mails, labels, models, pause) -> list[dict]:
    """A predicted deadline is correct if its date matches a gold date of the same mail
    (each gold date can be matched once)."""
    rows = []
    for name in models:
        tp = n_pred = n_gold = failed = 0
        done = 0
        for mail in mails:
            try:
                predicted = extract_deadlines(mail, LLMOptions(model=name))
                time.sleep(pause)
            except LLMError as e:
                failed += 1
                if done == 0:
                    print(f"  {name}: skipped ({e})")
                    break
                continue
            done += 1
            gold = Counter(d["due_date"] for d in labels[mail.id]["deadlines"])
            pred = Counter(d.due_iso[:10] for d in predicted)
            tp += sum((gold & pred).values())
            n_pred += sum(pred.values())
            n_gold += sum(gold.values())
        if done == 0:
            rows.append({"model": name, "mails": 0, "precision": "skipped", "recall": "skipped",
                         "f1": "skipped", "failed_calls": failed})
            continue
        p = tp / n_pred if n_pred else 0.0
        r = tp / n_gold if n_gold else 0.0
        rows.append({"model": name, "mails": done, "gold": n_gold, "predicted": n_pred,
                     "precision": round(p, 3), "recall": round(r, 3),
                     "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0,
                     "failed_calls": failed})
        print(f"  deadlines {name}: {rows[-1]}")
    return rows


# ---------------- retrieval ----------------

def eval_retrieval() -> list[dict]:
    """Doc-level recall@k: share of a query's relevant files that appear in the top-k chunks."""
    queries = json.loads((ROOT / "data/retrieval_eval.json").read_text())
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
        row = {"mode": mode, "queries": len(queries)}
        row.update({f"recall@{k}": round(statistics.mean(recalls[k]), 3) for k in KS})
        row["mrr"] = round(statistics.mean(rr), 3)
        rows.append(row)
        print(f"  retrieval {mode}: {row}")
    return rows


# ---------------- reply drafts ----------------

def judge(draft_body: str, mail, chunks, judge_model: str) -> dict:
    prompt = render_prompt("judge", context=format_context(chunks), subject=mail.subject,
                           body=mail.body, draft=draft_body)
    data = parse_json(complete(prompt, LLMOptions(model=judge_model)))
    return {"faithfulness": int(data.get("faithfulness", 0)),
            "helpfulness": int(data.get("helpfulness", 0))}


def eval_drafts(mails, labels, models, judge_model, limit, pause):
    to_reply = [m for m in mails if labels[m.id]["needs_reply"]][:limit]
    retriever = get_retriever()
    summary, detail = [], []
    for name in models:
        opts = LLMOptions(model=name)
        scores = {"rag": [], "no_rag": []}
        issues = {"rag": 0, "no_rag": 0}
        try:
            for mail in to_reply:
                category = labels[mail.id]["category"]
                query = f"{mail.subject}\n{mail.body[:1000]}"
                for cond in ("rag", "no_rag"):
                    chunks, style = [], []
                    if cond == "rag":
                        chunks = retriever.search(query, k=settings.top_k, category=category,
                                                  contact=mail.sender)
                        style = retriever.search(query, k=2, contact=mail.sender, doc_type="reply")
                    email = draft_reply(mail, chunks, style, settings.tone, settings.user_name,
                                        "", opts)
                    # The judge sees the same full context for both conditions, so a no-RAG draft
                    # is not penalized for facts it could not know, only for invented ones.
                    judge_chunks = chunks or retriever.search(query, k=settings.top_k,
                                                              category=category,
                                                              contact=mail.sender)
                    grade = judge(email.body, mail, judge_chunks, judge_model)
                    time.sleep(pause)
                    scores[cond].append(grade)
                    issues[cond] += len(email.issues)
                    detail.append({"model": name, "mail_id": mail.id, "condition": cond,
                                   **grade, "guardrail_issues": len(email.issues),
                                   "sources": ";".join(c.source for c in chunks),
                                   "draft": email.body})
        except LLMError as e:
            print(f"  drafts {name}: stopped ({e})")
        for cond in ("rag", "no_rag"):
            graded = scores[cond]
            summary.append({
                "model": name, "condition": cond, "drafts": len(graded), "judge": judge_model,
                "faithfulness": round(statistics.mean(g["faithfulness"] for g in graded), 2)
                if graded else "skipped",
                "helpfulness": round(statistics.mean(g["helpfulness"] for g in graded), 2)
                if graded else "skipped",
                "guardrail_issues": issues[cond],
            })
            print(f"  drafts {name}/{cond}: {summary[-1]}")
    return summary, detail


def manual_summary() -> list[dict]:
    """Average manual 1-5 ratings from results/manual_ratings.csv (filled in by hand)."""
    path = RESULTS / "manual_ratings.csv"
    if not path.exists():
        return []
    rows = [r for r in csv.DictReader(open(path, encoding="utf-8")) if r.get("rating", "").strip()]
    out = []
    for key in sorted({(r["model"], r["condition"]) for r in rows}):
        ratings = [int(r["rating"]) for r in rows if (r["model"], r["condition"]) == key]
        out.append({"model": key[0], "condition": key[1], "rated": len(ratings),
                    "mean_rating": round(statistics.mean(ratings), 2)})
    return out


def write_manual_template(detail: list[dict], n: int = 10) -> None:
    path = RESULTS / "manual_ratings.csv"
    if path.exists() or not detail:
        return  # never overwrite ratings someone already typed in
    rows = [{"model": d["model"], "mail_id": d["mail_id"], "condition": d["condition"],
             "rating": "", "draft": d["draft"]} for d in detail[: n * 2]]
    write_csv("manual_ratings.csv", rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="*", default=[], help="LiteLLM model names")
    parser.add_argument("--judge", default=None, help="judge model (default: first --models)")
    parser.add_argument("--draft-limit", type=int, default=25)
    parser.add_argument("--sleep", type=float, default=0.0, help="seconds between LLM calls")
    parser.add_argument("--skip-drafts", action="store_true")
    args = parser.parse_args()

    RESULTS.mkdir(exist_ok=True)
    db.init_db()
    mails, labels = load_data()
    print(f"{len(mails)} labeled mails, models: {args.models or 'none (baseline only)'}")

    sections = []
    print("retrieval")
    retrieval = eval_retrieval()
    write_csv("retrieval.csv", retrieval)
    sections.append(("Retrieval: hybrid vs vector vs BM25 (doc-level recall@k, MRR)", retrieval))

    print("classification")
    classification = eval_classification(mails, labels, args.models, args.sleep)
    write_csv("classification.csv", classification)
    sections.append(("Classification (5 categories)", classification))

    if args.models:
        print("deadlines")
        deadlines = eval_deadlines(mails, labels, args.models, args.sleep)
        write_csv("deadlines.csv", deadlines)
        sections.append(("Deadline extraction (date match)", deadlines))

    if args.models and not args.skip_drafts:
        print("drafts")
        summary, detail = eval_drafts(mails, labels, args.models, args.judge or args.models[0],
                                      args.draft_limit, args.sleep)
        write_csv("drafts.csv", summary)
        write_csv("drafts_detail.csv", detail)
        write_manual_template(detail)
        sections.append(("Reply drafts: RAG vs no RAG (LLM-as-judge, 1-5)", summary))

    manual = manual_summary()
    if manual:
        sections.append(("Reply drafts: manual rating (1-5)", manual))

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    text = [f"# MailPilot eval results\n\nGenerated by `eval/run_eval.py` on {stamp}. "
            f"Dataset: {len(mails)} labeled mails in `data/sample_mails.json`.\n"]
    for title, rows in sections:
        text.append(f"## {title}\n\n{md_table(rows)}")
    (RESULTS / "summary.md").write_text("\n".join(text), encoding="utf-8")
    print(f"wrote {RESULTS / 'summary.md'}")


if __name__ == "__main__":
    main()
