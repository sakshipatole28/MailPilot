import { useEffect, useState } from "react";
import { api } from "../../shared/api";
import { inView, scoreClass, sortMails, type SortBy, type View, VIEWS } from "../../shared/inbox";
import type { Brief, Mail, TriageStatus } from "../../shared/types";
import { CategoryBadge, messageOf, Notice } from "../ui";

export function Inbox({ onOpen }: { onOpen: (mail: Mail) => void }) {
  const [mails, setMails] = useState<Mail[]>([]);
  const [brief, setBrief] = useState<Brief | null>(null);
  const [triage, setTriage] = useState<TriageStatus | null>(null);
  const [view, setView] = useState<View>("all");
  const [category, setCategory] = useState("All");
  const [sortBy, setSortBy] = useState<SortBy>("priority");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  async function load() {
    try {
      const [m, b, t] = await Promise.all([api.mails(), api.brief(), api.triageStatus()]);
      setMails(m);
      setBrief(b);
      setTriage(t);
      setError("");
    } catch (e) {
      setError(messageOf(e));
    }
  }

  useEffect(() => {
    load();
  }, []);

  // While the backend is triaging in the background, refresh every few seconds.
  const working = (triage?.pending ?? 0) > 0;
  useEffect(() => {
    if (!working) return;
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, [working]);

  async function run(task: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await task();
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(false);
      await load();
    }
  }

  const sync = () =>
    run(async () => {
      const r = await api.sync();
      setStatus(r.new ? `${r.new} new mail. Triaging in the background…` : "No new mail.");
    });

  // For when background triage cannot run (e.g. your API key lives only in this browser).
  const triageNow = () =>
    run(async () => {
      const r = await api.triage(10);
      setStatus(`Triaged ${r.triaged}. ${r.remaining} left.`);
    });

  const categories = ["All", ...new Set(mails.map((m) => m.category ?? "Other"))];
  const shown = sortMails(
    mails.filter((m) => inView(m, view) && (category === "All" || m.category === category)),
    sortBy,
  );

  return (
    <section>
      {brief && (
        <div className="brief">
          <button className="stat" onClick={() => setView("reply")}>
            <strong>{brief.needs_reply.length}</strong> to reply
          </button>
          <button className="stat" onClick={() => setView("tasks")}>
            <strong>{brief.due_soon.length}</strong> due in 3 days
          </button>
          <button className={`stat ${brief.suspicious.length ? "alert" : ""}`} onClick={() => setView("suspicious")}>
            <strong>{brief.suspicious.length}</strong> suspicious
          </button>
          <span className="stat muted">
            <strong>{brief.unread}</strong> unread
          </span>
        </div>
      )}

      <div className="row">
        <button onClick={sync} disabled={busy}>Sync</button>
        {(triage?.failed ?? 0) + (triage?.new ?? 0) > 0 && (
          <button onClick={triageNow} disabled={busy}>Triage now</button>
        )}
        <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Category">
          {categories.map((c) => <option key={c}>{c}</option>)}
        </select>
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value as SortBy)} aria-label="Sort">
          <option value="priority">Priority</option>
          <option value="newest">Newest</option>
        </select>
      </div>

      <div className="chips">
        {VIEWS.map((v) => (
          <button key={v.id} className={`chip ${view === v.id ? "on" : ""}`} onClick={() => setView(v.id)}>
            {v.label}
          </button>
        ))}
      </div>

      {working && (
        <div className="progress">
          <div style={{ width: `${(100 * (triage!.done)) / Math.max(1, triage!.done + triage!.pending)}%` }} />
          <span>AI triage: {triage!.done} done, {triage!.pending} to go</span>
        </div>
      )}
      <Notice error={error} status={status} />
      {!mails.length && !error && <p className="muted">No mail yet. Press Sync.</p>}
      {mails.length > 0 && !shown.length && <p className="muted">Nothing here.</p>}

      <ul className="list">
        {shown.map((m) => (
          <li key={m.id} className={m.is_read ? "" : "unread"} onClick={() => onOpen(m)}>
            <div className="row spread">
              <span className="sender">{m.sender_name || m.sender}</span>
              <span className="muted small">{new Date(m.received_at).toLocaleDateString()}</span>
            </div>
            <div className="subject">{m.subject}</div>
            {m.summary && <div className="summary">{m.summary}</div>}
            <div className="row">
              <span className={scoreClass(m.priority_score)} title={m.priority_reasons.join("\n")}>
                {m.priority_score ?? "…"}
              </span>
              <CategoryBadge category={m.category} />
              {m.risk_level === "high" && <span className="badge danger">⚠ phishing?</span>}
              {m.risk_level === "medium" && <span className="badge warn">check sender</span>}
              {m.needs_reply && !m.replied && <span className="badge">reply</span>}
              {m.intents.includes("meeting") && <span className="badge">meeting</span>}
              {m.intents.includes("task") && <span className="badge">task</span>}
              {m.replied && <span className="badge done">replied</span>}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
