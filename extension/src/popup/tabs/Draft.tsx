import { useEffect, useState } from "react";
import { api } from "../../shared/api";
import { timeAgo } from "../../shared/format";
import { unsubscribeUrl } from "../../shared/inbox";
import type { Category, GeneratedEmail, Mail } from "../../shared/types";
import { BackIcon, ShieldIcon, SparkIcon } from "../icons";
import { Avatar, CategoryBadge, GeneratedView, messageOf, Notice, priorityClass } from "../ui";

export function Draft({ mail, onChange, onBack }: {
  mail: Mail;
  onChange: (m: Mail) => void;
  onBack: () => void;
}) {
  const [instruction, setInstruction] = useState("");
  const [useRag, setUseRag] = useState(true);
  const [draft, setDraft] = useState<GeneratedEmail | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [showMail, setShowMail] = useState(false);
  const [rated, setRated] = useState(0);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api.settings().then((s) => setCategories(s.categories)).catch(() => undefined);
    if (!mail.is_read) api.updateMail(mail.id, { is_read: true }).then(onChange).catch(() => {});
  }, [mail.id]);

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
      setDraft(await api.draft(mail.id, instruction, useRag));
      setRated(0);
    });

  const findTasks = () =>
    run(async () => {
      const found = await api.extractDeadlines(mail.id);
      setStatus(found.length ? `Added ${found.length} task${found.length > 1 ? "s" : ""}` : "No tasks in this mail");
      chrome.runtime.sendMessage({ type: "refresh-deadlines" }).catch(() => undefined);
    });

  const markReplied = () => run(async () => onChange(await api.updateMail(mail.id, { replied: true })));

  // A correction is stored and shown to the AI as an example for similar mail.
  const correct = (category: string) =>
    run(async () => {
      onChange(await api.updateMail(mail.id, { category }));
      setStatus(`Got it. Similar mail will go to "${category}"`);
    });

  async function rate(rating: number) {
    if (!draft?.draft_id) return;
    await api.feedback(draft.draft_id, rating);
    setRated(rating);
  }

  const unsubscribe = unsubscribeUrl(mail);
  return (
    <section className="detail">
      <button className="back" onClick={onBack}><BackIcon /> Back</button>

      <div className={`card mail-card ${priorityClass(mail.priority_score)}`}>
        <div className="mail-card-head">
          <Avatar name={mail.sender_name} email={mail.sender} />
          <div className="grow">
            <div className="sender">{mail.sender_name || mail.sender}</div>
            <div className="muted tiny">{mail.sender} · {timeAgo(mail.received_at)}</div>
          </div>
          {mail.priority_score !== null && (
            <span className="score-badge" title={mail.priority_reasons.join("\n")}>{mail.priority_score}</span>
          )}
        </div>
        <h2 className="mail-subject">{mail.subject}</h2>
        {mail.summary && <p className="ai-summary"><SparkIcon /> {mail.summary}</p>}
        <div className="tags">
          <CategoryBadge category={mail.category} />
          {mail.intents.filter((i) => i !== "fyi").map((i) => <span key={i} className="chip-tag plain">{i}</span>)}
          {unsubscribe && <a className="tiny" href={unsubscribe} target="_blank" rel="noreferrer">Unsubscribe</a>}
        </div>
        <button className="link" onClick={() => setShowMail(!showMail)}>{showMail ? "Hide" : "Show"} full mail</button>
        {showMail && <pre className="mail-body">{mail.body}</pre>}
      </div>

      {mail.risk_level && mail.risk_level !== "low" && (
        <div className={`callout ${mail.risk_level === "high" ? "danger" : "warn"}`}>
          <strong><ShieldIcon /> {mail.risk_level === "high" ? "This looks like phishing" : "Be careful with this sender"}</strong>
          <ul>{mail.risk_reasons.map((r) => <li key={r}>{r}</li>)}</ul>
        </div>
      )}

      <div className="card">
        <div className="composer">
          <input
            placeholder="Anything to add? e.g. accept the Thursday slot"
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !busy && generate()}
          />
          <button className="primary" onClick={generate} disabled={busy}>
            {busy && !draft ? "Writing…" : draft ? "Rewrite" : "✨ Draft reply"}
          </button>
        </div>
        <label className="toggle">
          <input type="checkbox" checked={useRag} onChange={(e) => setUseRag(e.target.checked)} />
          <span>Use my notes (resume, availability, past replies)</span>
        </label>
      </div>

      <Notice error={error} status={status} />

      {draft && (
        <>
          {draft.quick_replies.length > 0 && (
            <div className="chips">
              <span className="muted tiny">Quick replies:</span>
              {draft.quick_replies.map((q) => (
                <button key={q} className="chip" onClick={() => setDraft({ ...draft, body: q })}>{q}</button>
              ))}
            </div>
          )}
          {draft.revisions > 0 && (
            <p className="muted tiny">
              ✓ Fact-checked: fixed {draft.first_pass_issues} unsupported detail
              {draft.first_pass_issues === 1 ? "" : "s"} before showing you this.
            </p>
          )}
          <GeneratedView email={draft} onEdit={setDraft} />
          <div className="rating">
            <span className="muted tiny">How good is this draft?</span>
            {[1, 2, 3, 4, 5].map((n) => (
              <button key={n} className={`star ${rated >= n ? "on" : ""}`} onClick={() => rate(n)} aria-label={`${n} stars`}>★</button>
            ))}
          </div>
        </>
      )}

      <div className="card actions">
        <button onClick={findTasks} disabled={busy}>Find tasks</button>
        <button onClick={markReplied} disabled={busy || mail.replied}>{mail.replied ? "✓ Replied" : "Mark replied"}</button>
        <label className="inline">
          Category
          <select value={mail.category ?? ""} onChange={(e) => correct(e.target.value)} disabled={busy}>
            {categories.map((c) => <option key={c.name}>{c.name}</option>)}
          </select>
        </label>
      </div>
      {mail.priority_reasons.length > 0 && (
        <details className="why">
          <summary>Why priority {mail.priority_score}?</summary>
          <ul>{mail.priority_reasons.map((r) => <li key={r}>{r}</li>)}</ul>
        </details>
      )}
    </section>
  );
}
