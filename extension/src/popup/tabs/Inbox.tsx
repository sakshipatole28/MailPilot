import { useEffect, useState } from "react";
import { api } from "../../shared/api";
import { matchesSearch, timeAgo } from "../../shared/format";
import { inView, sortMails, type SortBy, type View, VIEWS } from "../../shared/inbox";
import type { Brief, Mail, TriageStatus } from "../../shared/types";
import { SearchIcon, ShieldIcon, SyncIcon } from "../icons";
import { Avatar, CategoryBadge, EmptyState, messageOf, Notice, priorityClass, Skeleton } from "../ui";

function MailRow({ mail, onOpen }: { mail: Mail; onOpen: () => void }) {
  return (
    <li className={`mail ${mail.is_read ? "" : "unread"} ${priorityClass(mail.priority_score)}`} onClick={onOpen}>
      <Avatar name={mail.sender_name} email={mail.sender} />
      <div className="mail-main">
        <div className="mail-top">
          <span className="sender">{mail.sender_name || mail.sender}</span>
          <span className="time">{timeAgo(mail.received_at)}</span>
        </div>
        <div className="subject">{mail.subject}</div>
        <div className="summary">{mail.summary || (mail.triage_status === "pending" ? "Reading…" : mail.body.slice(0, 90))}</div>
        <div className="tags">
          {mail.risk_level === "high" && <span className="chip-tag danger"><ShieldIcon /> Phishing?</span>}
          {mail.risk_level === "medium" && <span className="chip-tag warn">Check sender</span>}
          <CategoryBadge category={mail.category} />
          {mail.needs_reply && !mail.replied && <span className="chip-tag plain">↩ Reply</span>}
          {mail.intents.includes("meeting") && <span className="chip-tag plain">📅 Meeting</span>}
          {mail.intents.includes("task") && <span className="chip-tag plain">✓ Task</span>}
          {mail.replied && <span className="chip-tag done">Replied</span>}
        </div>
      </div>
    </li>
  );
}

export function Inbox({ onOpen }: { onOpen: (mail: Mail) => void }) {
  const [mails, setMails] = useState<Mail[] | null>(null);
  const [brief, setBrief] = useState<Brief | null>(null);
  const [triage, setTriage] = useState<TriageStatus | null>(null);
  const [view, setView] = useState<View>("all");
  const [category, setCategory] = useState("All");
  const [sortBy, setSortBy] = useState<SortBy>("priority");
  const [query, setQuery] = useState("");
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
      setMails((current) => current ?? []);
    }
  }

  useEffect(() => {
    load();
  }, []);

  // While the backend triages in the background, refresh every few seconds.
  const working = (triage?.pending ?? 0) > 0;
  useEffect(() => {
    if (!working) return;
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, [working]);

  async function sync() {
    setBusy(true);
    setError("");
    try {
      const r = await api.sync();
      setStatus(r.new ? `${r.new} new mail` : "You're up to date");
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(false);
      await load();
    }
  }

  // For when background triage cannot run (e.g. your API key lives only in this browser).
  async function triageNow() {
    setBusy(true);
    try {
      const r = await api.triage(10);
      setStatus(`Sorted ${r.triaged} more mails`);
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(false);
      await load();
    }
  }

  const all = mails ?? [];
  const categories = ["All", ...new Set(all.map((m) => m.category ?? "Other"))];
  const shown = sortMails(
    all.filter((m) => inView(m, view) && (category === "All" || m.category === category) && matchesSearch(m, query)),
    sortBy,
  );
  const done = triage?.done ?? 0;
  const total = done + (triage?.pending ?? 0);
  const stuck = (triage?.failed ?? 0) + (triage?.new ?? 0) > 0 && !working;

  return (
    <section>
      <div className="inbox-head">
        <div className="search">
          <SearchIcon />
          <input placeholder="Search mail" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <button className="icon-btn" onClick={sync} disabled={busy} title="Sync now" aria-label="Sync now">
          <span className={busy ? "spin" : ""}><SyncIcon /></span>
        </button>
      </div>

      {brief && (
        <div className="stats">
          <button className={`stat ${view === "reply" ? "on" : ""}`} onClick={() => setView(view === "reply" ? "all" : "reply")}>
            <strong>{brief.needs_reply.length}</strong><span>to reply</span>
          </button>
          <button className={`stat ${view === "tasks" ? "on" : ""}`} onClick={() => setView(view === "tasks" ? "all" : "tasks")}>
            <strong>{brief.due_soon.length}</strong><span>due soon</span>
          </button>
          <button className={`stat ${brief.suspicious.length ? "alert" : ""} ${view === "suspicious" ? "on" : ""}`}
            onClick={() => setView(view === "suspicious" ? "all" : "suspicious")}>
            <strong>{brief.suspicious.length}</strong><span>suspicious</span>
          </button>
          <div className="stat static"><strong>{brief.unread}</strong><span>unread</span></div>
        </div>
      )}

      {working && (
        <div className="progress" title="AI is reading your new mail">
          <div className="bar" style={{ width: `${(100 * done) / Math.max(1, total)}%` }} />
          <span>✨ Sorting your mail… {done}/{total}</span>
        </div>
      )}
      {stuck && (
        <button className="banner" onClick={triageNow} disabled={busy}>
          Some mail isn't sorted yet. <u>Sort now</u>
        </button>
      )}

      <div className="chips">
        {VIEWS.map((v) => (
          <button key={v.id} className={`chip ${view === v.id ? "on" : ""}`} onClick={() => setView(v.id)}>
            {v.label}
          </button>
        ))}
      </div>
      <div className="filters">
        <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Category">
          {categories.map((c) => <option key={c}>{c}</option>)}
        </select>
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value as SortBy)} aria-label="Sort">
          <option value="priority">Most important first</option>
          <option value="newest">Newest first</option>
        </select>
      </div>

      <Notice error={error} status={status} />
      {mails === null ? (
        <Skeleton />
      ) : !all.length ? (
        <EmptyState emoji="📭" title="No mail yet">Press sync to load your inbox.</EmptyState>
      ) : !shown.length ? (
        <EmptyState emoji="🎉" title={view === "all" && !query ? "Nothing here" : "All clear"}>
          {query ? "No mail matches your search." : "Nothing in this view right now."}
        </EmptyState>
      ) : (
        <ul className="mail-list">
          {shown.map((m) => <MailRow key={m.id} mail={m} onOpen={() => onOpen(m)} />)}
        </ul>
      )}
    </section>
  );
}
