import { useEffect, useState } from "react";
import { api } from "../../shared/api";
import { scoreClass, unsubscribeUrl } from "../../shared/inbox";
import type { Category, GeneratedEmail, Mail } from "../../shared/types";
import { CategoryBadge, GeneratedView, messageOf, Notice } from "../ui";

export function Draft({ mail, onChange }: { mail: Mail | null; onChange: (m: Mail) => void }) {
  const [instruction, setInstruction] = useState("");
  const [useRag, setUseRag] = useState(true);
  const [draft, setDraft] = useState<GeneratedEmail | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [rated, setRated] = useState(0);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api.settings().then((s) => setCategories(s.categories)).catch(() => undefined);
  }, []);

  useEffect(() => {
    setDraft(null);
    setRated(0);
    setStatus("");
    setError("");
    if (mail && !mail.is_read) api.updateMail(mail.id, { is_read: true }).then(onChange).catch(() => {});
  }, [mail?.id]);

  if (!mail) return <p className="muted">Pick a mail in the Inbox tab.</p>;

  async function run(task: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await task();
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(false);
    }
  }

  const generate = () =>
    run(async () => {
      setStatus("Drafting…");
      setDraft(await api.draft(mail.id, instruction, useRag));
      setRated(0);
      setStatus("");
    });

  const findTasks = () =>
    run(async () => {
      const found = await api.extractDeadlines(mail.id);
      setStatus(found.length ? `Tasks: ${found.map((d) => d.title).join(", ")}` : "No tasks found");
      chrome.runtime.sendMessage({ type: "refresh-deadlines" }).catch(() => undefined);
    });

  const markReplied = () => run(async () => onChange(await api.updateMail(mail.id, { replied: true })));

  // A correction is stored and shown to the AI as an example for similar mail.
  const correct = (category: string) =>
    run(async () => {
      onChange(await api.updateMail(mail.id, { category }));
      setStatus(`Saved. Similar mail will be sorted into "${category}".`);
    });

  async function rate(rating: number) {
    if (!draft?.draft_id) return;
    await api.feedback(draft.draft_id, rating);
    setRated(rating);
  }

  const unsubscribe = unsubscribeUrl(mail);
  return (
    <section>
      <div className="mail-head">
        <div className="subject">{mail.subject}</div>
        <div className="muted small">
          {mail.sender_name} &lt;{mail.sender}&gt; · {new Date(mail.received_at).toLocaleString()}
        </div>
        {mail.summary && <p className="summary">{mail.summary}</p>}
        <div className="row">
          <span className={scoreClass(mail.priority_score)}>{mail.priority_score ?? "…"}</span>
          <CategoryBadge category={mail.category} />
          {mail.intents.filter((i) => i !== "fyi").map((i) => <span key={i} className="badge">{i}</span>)}
          {unsubscribe && (
            <a className="small" href={unsubscribe} target="_blank" rel="noreferrer">Unsubscribe</a>
          )}
        </div>
      </div>

      {mail.risk_level && mail.risk_level !== "low" && (
        <div className={`notice ${mail.risk_level === "high" ? "error" : "warn"}`}>
          <strong>{mail.risk_level === "high" ? "Likely phishing or scam" : "Check the sender"}</strong>
          <ul>{mail.risk_reasons.map((r) => <li key={r}>{r}</li>)}</ul>
        </div>
      )}

      <details>
        <summary>Show mail</summary>
        <pre className="mail-body">{mail.body}</pre>
      </details>
      {mail.priority_reasons.length > 0 && (
        <details>
          <summary>Why this priority</summary>
          <ul className="small">{mail.priority_reasons.map((r) => <li key={r}>{r}</li>)}</ul>
        </details>
      )}
      <label className="row small">
        Category
        <select value={mail.category ?? ""} onChange={(e) => correct(e.target.value)} disabled={busy}>
          {categories.map((c) => <option key={c.name}>{c.name}</option>)}
        </select>
        {mail.classified_by === "user" && <span className="muted">(your correction)</span>}
      </label>

      <input
        placeholder="Optional instruction, e.g. accept the Thursday slot"
        value={instruction}
        onChange={(e) => setInstruction(e.target.value)}
      />
      <div className="row">
        <button className="primary" onClick={generate} disabled={busy}>Draft reply</button>
        <button onClick={findTasks} disabled={busy}>Find tasks</button>
        <button onClick={markReplied} disabled={busy || mail.replied}>
          {mail.replied ? "Replied" : "Mark replied"}
        </button>
        <label className="small">
          <input type="checkbox" checked={useRag} onChange={(e) => setUseRag(e.target.checked)} />
          use my notes
        </label>
      </div>
      <Notice error={error} status={status} />

      {draft && (
        <>
          {draft.quick_replies.length > 0 && (
            <div className="chips">
              <span className="muted small">Quick reply:</span>
              {draft.quick_replies.map((q) => (
                <button key={q} className="chip" onClick={() => setDraft({ ...draft, body: q })}>{q}</button>
              ))}
            </div>
          )}
          {draft.revisions > 0 && (
            <p className="muted small">
              Self-checked: the first draft stated {draft.first_pass_issues} thing
              {draft.first_pass_issues === 1 ? "" : "s"} your mail and notes don't support, so it
              was revised {draft.revisions}×.
            </p>
          )}
          <GeneratedView email={draft} onEdit={setDraft} />
          <div className="row small">
            Rate this draft:
            {[1, 2, 3, 4, 5].map((n) => (
              <button key={n} className={`star ${rated >= n ? "on" : ""}`} onClick={() => rate(n)}>
                {n}
              </button>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
