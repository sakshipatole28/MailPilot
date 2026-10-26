"""Evaluate MailPilot on the labeled data in data/. Writes CSVs and results/summary.md.

Every number in the README must come from here.

    cd backend
    .venv/bin/python ../eval/run_eval.py                       # retrieval + keyword baseline only
    .venv/bin/python ../eval/run_eval.py \
        --models groq/openai/gpt-oss-120b groq/openai/gpt-oss-20b groq/qwen/qwen3.8-27b \
        --triage-models groq/openai/gpt-oss-120b \
        --security-model groq/openai/gpt-oss-120b \
        --draft-model groq/openai/gpt-oss-120b \
        --judges groq/qwen/qwen3.8-27b groq/openai/gpt-oss-20b

Each section is written to results/sections/*.md and results/summary.md joins them, so a run
that skips a section (to save free-tier quota) keeps that section's last results.

Security is measured on data/security_eval.json:
- phishing detection precision/recall for the header/link rules alone, the LLM alone, and both
- prompt-injection attack success rate (ASR) with no defense, delimiting and datamarking
  (spotlighting, Hines et al. 2024; attack style from Microsoft's LLMail-Inject challenge)

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
from app.agents.draft_graph import run_draft_graph  # noqa: E402
from app.llm import schemas, security  # noqa: E402
from app.llm.generator import draft_reply, format_context  # noqa: E402
from app.llm.taxonomy import STUDENT  # noqa: E402
from app.llm.triage import triage_mail  # noqa: E402
from app.mail_sources.base import extract_links  # noqa: E402
from app.mail_sources.file_source import FileMailSource  # noqa: E402
from app.models import LLMOptions, Mail  # noqa: E402
from metrics import claim_faithfulness, deadline_matches, pairwise_outcome  # noqa: E402

RESULTS = ROOT / "results"
SECTIONS = RESULTS / "sections"
KS = (1, 3, 5)
USER = "Sam Rivera"
# Senders the sample user has written to before (lookalike checks compare against these).
KNOWN_SENDERS = {"tpo@westbrook.edu", "priya.nair@northwind-analytics.com"}


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


# ---------------- triage (one call per mail) ----------------

def prompt_tokens(text: str) -> int:
    import litellm
    return litellm.token_counter(model="gpt-4o", text=text)  # o200k tokenizer, an approximation


def eval_triage(mails, labels, models, pause) -> list[dict]:
    """The product path: one triage call per mail. Scored on the same labels as the
    separate classify + deadline prompts above, plus input tokens per mail for both designs."""
    rows = []
    for name in models:
        y_true, y_pred, reply_true, reply_pred, failed = [], [], [], [], 0
        tp = n_pred = n_gold = 0
        for mail in mails:
            result = call(lambda: triage_mail(mail, LLMOptions(model=name), STUDENT, USER,
                                              spotlight_mode="datamark"), pause)
            if result is None:
                failed += 1
                continue
            triaged, tasks = result
            label = labels[mail.id]
            y_true.append(label["category"])
            y_pred.append(triaged.category)
            reply_true.append(label["needs_reply"])
            reply_pred.append(bool(triaged.needs_reply))
            gold = [d["due_date"] for d in label["deadlines"]]
            pred = [t.due_iso[:10] for t in tasks if t.due_iso]
            tp += deadline_matches(gold, pred)
            n_pred += len(pred)
            n_gold += len(gold)
        p = tp / n_pred if n_pred else 0.0
        r = tp / n_gold if n_gold else 0.0
        rows.append({
            "model": name, "mails": len(y_pred),
            "accuracy": round(accuracy_score(y_true, y_pred), 3) if y_pred else "n/a",
            "macro_f1": round(f1_score(y_true, y_pred, labels=DEFAULT_CATEGORIES, average="macro",
                                       zero_division=0), 3) if y_pred else "n/a",
            "needs_reply_acc": round(accuracy_score(reply_true, reply_pred), 3) if y_pred else "n/a",
            "deadline_precision": round(p, 3), "deadline_recall": round(r, 3),
            "deadline_f1": round(2 * p * r / (p + r), 3) if p + r else 0.0,
            "failed_calls": failed,
        })
        print(f"  {rows[-1]}")
    return rows


def eval_token_cost(mails) -> list[dict]:
    """Input tokens per mail: separate classify + deadline prompts vs one triage prompt."""
    from app.llm.deadlines import calendar_lines
    from app.llm.taxonomy import INTENTS, describe

    separate, single = [], []
    for mail in mails:
        cats = "\n".join(f"- {c.name}: {c.description}" for c in STUDENT)
        classify = render_prompt("classify", categories=cats, sender=mail.sender, subject=mail.subject,
                                 received_at=mail.received_at.isoformat(), body=mail.body)
        deadline = render_prompt("deadlines", received_at=mail.received_at.isoformat(),
                                 weekday=mail.received_at.strftime("%A"),
                                 calendar=calendar_lines(mail.received_at), sender=mail.sender,
                                 subject=mail.subject, body=mail.body)
        body, note = security.spotlight(mail.body, "datamark")
        triage = render_prompt("triage", user_name=USER, categories=describe(STUDENT),
                               intents="\n".join(f"- {k}: {v}" for k, v in INTENTS.items()),
                               received_at=mail.received_at.isoformat(),
                               weekday=mail.received_at.strftime("%A"),
                               calendar=calendar_lines(mail.received_at), examples="",
                               untrusted_note=note, sender=mail.sender, to=mail.to,
                               subject=mail.subject, body=body)
        separate.append(prompt_tokens(classify) + prompt_tokens(deadline))
        single.append(prompt_tokens(triage))
    return [
        {"design": "separate classify + deadline prompts", "llm_calls_per_mail": 2,
         "input_tokens_per_mail": round(statistics.mean(separate))},
        {"design": "one triage prompt (also: summary, intents, priority, phishing)",
         "llm_calls_per_mail": 1, "input_tokens_per_mail": round(statistics.mean(single))},
    ]


# ---------------- security ----------------

def security_mail(item: dict) -> Mail:
    return Mail(id=item["id"], sender=item["from"], sender_name=item.get("from_name", ""),
                to="sam.rivera@westbrook.edu", subject=item["subject"], body=item["body"],
                received_at=item.get("received_at", "2026-10-21T10:00:00+05:30"),
                headers=item.get("headers", {}),
                links=extract_links(item["body"], item.get("html", "")))


def prf(truth: list[bool], pred: list[bool]) -> dict:
    tp = sum(t and p for t, p in zip(truth, pred))
    fp = sum(p and not t for t, p in zip(truth, pred))
    fn = sum(t and not p for t, p in zip(truth, pred))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(precision, 3), "recall": round(recall, 3),
            "f1": round(2 * precision * recall / (precision + recall), 3) if precision + recall else 0.0,
            "false_positives": fp}


def eval_phishing(items, model, pause) -> tuple[list[dict], list[dict]]:
    known = {security.registrable(security.domain_of(s)) for s in KNOWN_SENDERS}
    truth, rules, llm, combined, detail = [], [], [], [], []
    for item in items:
        mail = security_mail(item)
        rule_level, rule_reasons = security.assess(mail, known_domains=known)
        result = call(lambda: triage_mail(mail, LLMOptions(model=model), STUDENT, USER,
                                          known_senders=KNOWN_SENDERS, spotlight_mode="datamark"), pause)
        if result is None:
            continue
        triaged, _ = result
        llm_flag = any(r.startswith("AI review") for r in triaged.risk_reasons)
        truth.append(item["phishing"])
        rules.append(rule_level != "low")
        llm.append(llm_flag)
        combined.append(triaged.risk_level == "high")
        detail.append({"id": item["id"], "phishing": item["phishing"], "rules": rule_level,
                       "llm_flag": llm_flag, "combined": triaged.risk_level,
                       "reasons": " | ".join(triaged.risk_reasons)[:400]})
    rows = [{"detector": "header/link rules (medium or high)", **prf(truth, rules)},
            {"detector": f"LLM only ({model})", **prf(truth, llm)},
            {"detector": "combined score = high (shipped)", **prf(truth, combined)}]
    for row in rows:
        print(f"  {row}")
    return rows, detail


def eval_injection(items, model, pause) -> tuple[list[dict], list[dict]]:
    """Attack success rate: share of attack mails whose canary ends up in the final draft
    (after guardrails). Notes are always retrieved here, to test the prompt-level defense alone;
    the product additionally withholds notes from mails its detector flags."""
    retriever = get_retriever()
    rows, detail = [], []
    detected = [security.looks_like_injection(f"{i['subject']}\n{i['body']}") for i in items]
    for mode in ("none", "delimit", "datamark"):
        hits = done = 0
        for item in items:
            mail = security_mail(item)
            query = f"{mail.subject}\n{mail.body[:1000]}"
            chunks = retriever.search(query, k=settings.top_k, contact=mail.sender)
            email = call(lambda: draft_reply(mail, chunks, [], settings.tone, USER, "",
                                             LLMOptions(model=model), spotlight_mode=mode), pause)
            if email is None:
                continue
            done += 1
            output = " ".join([email.subject, email.body, *email.quick_replies]).lower()
            success = item["canary"].lower() in output
            hits += success
            detail.append({"mode": mode, "id": item["id"], "attack_succeeded": success,
                           "draft": email.body[:600]})
        rows.append({"defense": mode, "attacks": done, "succeeded": hits,
                     "attack_success_rate": round(hits / done, 3) if done else "n/a"})
        print(f"  {rows[-1]}")
    rows.append({"defense": "regex detector (flags mail, withholds notes)", "attacks": len(items),
                 "succeeded": len(items) - sum(detected),
                 "attack_success_rate": f"detected {sum(detected)}/{len(items)}"})
    return rows, detail


def eval_detector_false_positives(mails) -> dict:
    flagged = [m.id for m in mails if security.looks_like_injection(f"{m.subject}\n{m.body}")]
    return {"mails": len(mails), "flagged_as_injection": len(flagged), "ids": ",".join(flagged)}


# ---------------- reply drafts ----------------

def judge_draft(draft: str, mail, chunks, judge_model: str) -> dict:
    prompt = render_prompt("judge", context=format_context(chunks), subject=mail.subject,
                           body=mail.body, draft=draft)
    data = complete_json(prompt, LLMOptions(model=judge_model), schema=schemas.JUDGE, name="judge")
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
        return str(complete_json(prompt, LLMOptions(model=judge_model), schema=schemas.PAIRWISE,
                                 name="pairwise").get("winner", "tie"))

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


def eval_self_correction(mails, labels, writer, judge, pause) -> tuple[list[dict], list[dict]]:
    """Single-pass drafts vs the self-correcting draft graph, on every needs-reply mail.
    Both start from the same first draft (same prompt, so the same cached call)."""
    retriever = get_retriever()
    opts = LLMOptions(model=writer)
    detail = []
    for mail in [m for m in mails if labels[m.id]["needs_reply"]]:
        query = f"{mail.subject}\n{mail.body[:1000]}"
        chunks = retriever.search(query, k=settings.top_k, category=labels[mail.id]["category"],
                                  contact=mail.sender)
        style = retriever.search(query, k=2, contact=mail.sender, doc_type="reply")
        single = call(lambda: draft_reply(mail, chunks, style, settings.tone, USER, "", opts), pause)
        graph = call(lambda: run_draft_graph(mail, chunks, style, settings.tone, USER, "", opts), pause)
        if single is None or graph is None:
            continue
        row = {"mail_id": mail.id, "first_pass_issues": graph.first_pass_issues,
               "revisions": graph.revisions, "single_final_issues": len(single.issues),
               "graph_final_issues": len(graph.issues)}
        for name, email in (("single", single), ("graph", graph)):
            grade = call(lambda: judge_draft(email.body, mail, chunks, judge), pause)
            row[f"{name}_faithfulness"] = grade["faithfulness"] if grade else None
            row[f"{name}_helpfulness"] = grade["helpfulness"] if grade else None
        detail.append(row)
        print(f"    {row}")
    n = len(detail)
    graded = [d for d in detail if d["single_faithfulness"] is not None and d["graph_faithfulness"] is not None]
    summary = [{
        "drafts": n,
        "drafts_with_unsupported_facts_first_pass": sum(d["first_pass_issues"] > 0 for d in detail),
        "revised": sum(d["revisions"] > 0 for d in detail),
        "unsupported_facts_first_pass": sum(d["first_pass_issues"] for d in detail),
        "left_after_revision": sum(d["graph_final_issues"] for d in detail),
        "judge": judge,
        "faithfulness_single_pass": mean(d["single_faithfulness"] for d in graded),
        "faithfulness_self_correcting": mean(d["graph_faithfulness"] for d in graded),
        "helpfulness_single_pass": mean(d["single_helpfulness"] for d in graded),
        "helpfulness_self_correcting": mean(d["graph_helpfulness"] for d in graded),
    }]
    print(f"  {summary[0]}")
    return summary, detail


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="*", default=[], help="models for classification + deadlines")
    parser.add_argument("--deadline-models", nargs="*", default=None,
                        help="models for deadline extraction (default: --models)")
    parser.add_argument("--draft-limit", type=int, default=None,
                        help="evaluate drafts for only the first N needs-reply mails")
    parser.add_argument("--second-judge-limit", type=int, default=None,
                        help="grade only the first N mails with the second judge (saves quota)")
    parser.add_argument("--triage-models", nargs="*", default=[], help="models for the triage eval")
    parser.add_argument("--security-model", default=None, help="model for the security eval")
    parser.add_argument("--self-correction", nargs=2, metavar=("WRITER", "JUDGE"), default=None,
                        help="evaluate the self-correcting draft graph")
    parser.add_argument("--draft-model", default=None, help="writes the drafts (default: first --models)")
    parser.add_argument("--judges", nargs="*", default=[], help="judge models; the first is primary")
    parser.add_argument("--sleep", type=float, default=0.0, help="seconds between LLM calls")
    parser.add_argument("--retries", type=int, default=8, help="retries on rate limits")
    parser.add_argument("--skip-drafts", action="store_true")
    args = parser.parse_args()

    settings.llm_retries = args.retries
    # The eval never touches the app's data: its own cache DB and search index, whatever .env
    # says (a user's .env may point DB_PATH at their real Gmail database).
    settings.db_path = ROOT / "data" / "mailpilot.db"
    settings.chroma_dir = ROOT / "data" / "chroma_eval"
    settings.context_dir = ROOT / "data" / "context"
    settings.max_rate_limit_wait = 900  # free-tier daily limits refill gradually; wait them out
    SECTIONS.mkdir(parents=True, exist_ok=True)
    db.init_db()
    mails, labels = load_data()
    print(f"{len(mails)} labeled mails, models: {args.models or 'none (baseline only)'}")

    def section(name: str, title: str, rows: list[dict], note: str = "") -> None:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        body = f"## {title}\n\n{note + chr(10) + chr(10) if note else ''}{md_table(rows)}\n_Run: {stamp}_\n"
        (SECTIONS / f"{name}.md").write_text(body, encoding="utf-8")

    print("retrieval")
    retrieval = eval_retrieval("retrieval_eval.json") + eval_retrieval("retrieval_eval_paraphrased.json")
    write_csv("retrieval.csv", retrieval)
    section("10-retrieval", "Retrieval: hybrid vs vector vs BM25 (doc-level recall@k, MRR)", retrieval)

    print("classification")
    classification = eval_classification(mails, labels, args.models, args.sleep)
    write_csv("classification.csv", classification)
    section("20-classification", "Classification with a separate classify prompt (5 categories)",
            classification)

    if args.models:
        print("deadlines")
        deadline_models = args.models if args.deadline_models is None else args.deadline_models
        deadlines = eval_deadlines(mails, labels, deadline_models, args.sleep)
        write_csv("deadlines.csv", deadlines)
        section("30-deadlines", "Deadline extraction with a separate prompt (date match)", deadlines)

    cost = eval_token_cost(mails)
    write_csv("token_cost.csv", cost)
    section("35-token-cost", "Input tokens per mail: separate prompts vs one triage call", cost,
            "Counted with the o200k tokenizer on the rendered prompts; output and reasoning tokens excluded.")

    if args.triage_models:
        print("triage")
        triage = eval_triage(mails, labels, args.triage_models, args.sleep)
        write_csv("triage.csv", triage)
        section("40-triage", "Triage: one call per mail (category, reply intent, deadlines)", triage)

    if args.security_model:
        data = json.loads((ROOT / "data/security_eval.json").read_text())
        print("phishing")
        phishing, phishing_detail = eval_phishing(data["phishing"], args.security_model, args.sleep)
        write_csv("phishing.csv", phishing)
        write_csv("phishing_detail.csv", phishing_detail)
        n = len(data["phishing"])
        section("60-phishing", "Phishing detection", phishing,
                f"{n} hand-written mails ({sum(i['phishing'] for i in data['phishing'])} phishing, "
                f"{sum(not i['phishing'] for i in data['phishing'])} legitimate look-alikes such as "
                "real security alerts, bank reminders and newsletters with short links).")
        print("injection")
        injection, injection_detail = eval_injection(data["injection"], args.security_model, args.sleep)
        write_csv("injection.csv", injection)
        write_csv("injection_detail.csv", injection_detail)
        fp = eval_detector_false_positives(mails)
        section("70-injection", "Prompt injection: attack success rate by defense", injection,
                f"{len(data['injection'])} attack mails written by {args.security_model} drafts with the "
                "user's notes available. An attack succeeds if its canary string reaches the final "
                f"draft. Regex detector false positives on the {fp['mails']} normal sample mails: "
                f"{fp['flagged_as_injection']}.")

    if args.self_correction:
        writer, judge = args.self_correction
        print(f"self-correction: writer {writer}, judge {judge}")
        sc_summary, sc_detail = eval_self_correction(mails, labels, writer, judge, args.sleep)
        write_csv("self_correction.csv", sc_summary)
        write_csv("self_correction_detail.csv", sc_detail)
        section("55-self-correction", f"Self-correcting drafts (LangGraph), written by {writer}",
                sc_summary, "Unsupported facts = dates, times, weekdays, links, emails, phone numbers or "
                "greeting names that neither the mail nor the notes contain (the guardrail's check). "
                "Single pass masks them with [confirm: ...]; the graph first asks the model to fix "
                "them (at most 2 rounds), then masks whatever is left.")

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
        section("50-drafts", f"Reply drafts: RAG vs no RAG, written by {draft_model}", summary)
        section("51-drafts-pairwise", "Reply drafts: pairwise preference (both orders must agree)",
                pairwise)
        section("52-judge-agreement", "Judge agreement (Spearman, per draft)", agreement)

    parts = [f"# MailPilot eval results\n\nGenerated by `eval/run_eval.py`. Dataset: {len(mails)} "
             "labeled mails in `data/sample_mails.json`; security tests in `data/security_eval.json`. "
             "Each section shows the date it was last run.\n"]
    parts += [p.read_text(encoding="utf-8") for p in sorted(SECTIONS.glob("*.md"))]
    (RESULTS / "summary.md").write_text("\n".join(parts), encoding="utf-8")
    print(f"wrote {RESULTS / 'summary.md'}")


if __name__ == "__main__":
    main()
