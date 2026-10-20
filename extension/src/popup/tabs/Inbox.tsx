import { useEffect, useState } from "react";
import { api } from "../../shared/api";
import type { Mail } from "../../shared/types";
import { CategoryBadge, messageOf, Notice } from "../ui";

export function Inbox({ onOpen }: { onOpen: (mail: Mail) => void }) {
  const [mails, setMails] = useState<Mail[]>([]);
  const [filter, setFilter] = useState("All");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  async function load() {
    try {
      setMails(await api.mails());
    } catch (e) {
      setError(messageOf(e));
    }
  }

  useEffect(() => {
    load();
  }, []);

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
      const result = await api.sync();
      setStatus(`Synced: ${result.new} new of ${result.fetched}`);
    });

  // One request per mail so the user sees progress and a single failure doesn't lose the rest.
  const classifyAll = () =>
    run(async () => {
      const todo = shown.filter((m) => m.classified_by !== "llm");
      for (const [i, mail] of todo.entries()) {
        setStatus(`Classifying with AI ${i + 1}/${todo.length}…`);
        await api.classify(mail.id);
      }
      setStatus(todo.length ? `Classified ${todo.length} mails` : "All mails already AI-classified");
    });

  const categories = ["All", ...new Set(mails.map((m) => m.category ?? "Other"))];
  const shown = filter === "All" ? mails : mails.filter((m) => m.category === filter);

  return (
    <section>
      <div className="row">
        <button onClick={sync} disabled={busy}>Sync</button>
        <button onClick={classifyAll} disabled={busy || !shown.length}>Classify with AI</button>
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          {categories.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
      </div>
      <Notice error={error} status={status} />
      {!mails.length && !error && <p className="muted">No mail yet. Press Sync.</p>}
      <ul className="list">
        {shown.map((m) => (
          <li key={m.id} className={m.is_read ? "" : "unread"} onClick={() => onOpen(m)}>
            <div className="row spread">
              <span className="sender">{m.sender_name || m.sender}</span>
              <span className="muted">{new Date(m.received_at).toLocaleDateString()}</span>
            </div>
            <div className="subject">{m.subject}</div>
            <div className="row">
              <CategoryBadge category={m.category} />
              {m.priority === "high" && <span className="badge high">high</span>}
              {m.needs_reply && !m.replied && <span className="badge">needs reply</span>}
              {m.replied && <span className="badge done">replied</span>}
              {m.classified_by === "keywords" && <span className="muted small">keyword label</span>}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
