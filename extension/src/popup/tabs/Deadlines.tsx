import { useEffect, useState } from "react";
import { api } from "../../shared/api";
import { dueState } from "../../shared/reminders";
import type { Deadline } from "../../shared/types";
import { messageOf, Notice } from "../ui";

function refreshBackground() {
  chrome.runtime.sendMessage({ type: "refresh-deadlines" }).catch(() => undefined);
}

export function Deadlines() {
  const [items, setItems] = useState<Deadline[]>([]);
  const [showDone, setShowDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  async function load() {
    try {
      setItems(await api.deadlines(showDone));
    } catch (e) {
      setError(messageOf(e));
    }
  }

  useEffect(() => {
    load();
  }, [showDone]);

  // Scan every mail not scanned before (remembered locally), one request at a time.
  async function scan() {
    setBusy(true);
    setError("");
    try {
      const { scanned = [] } = (await chrome.storage.local.get("scanned")) as {
        scanned?: string[];
      };
      const todo = (await api.mails()).filter((m) => !scanned.includes(m.id));
      for (const [i, mail] of todo.entries()) {
        setStatus(`Scanning ${i + 1}/${todo.length}…`);
        await api.extractDeadlines(mail.id);
        scanned.push(mail.id);
        await chrome.storage.local.set({ scanned });
      }
      setStatus(todo.length ? `Scanned ${todo.length} mails` : "Nothing new to scan");
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(false);
      await load();
      refreshBackground();
    }
  }

  async function toggle(d: Deadline) {
    await api.setDeadlineDone(d.id, !d.done);
    await load();
    refreshBackground();
  }

  const now = new Date();
  return (
    <section>
      <div className="row">
        <button onClick={scan} disabled={busy}>Scan inbox for deadlines</button>
        <label className="small">
          <input type="checkbox" checked={showDone} onChange={(e) => setShowDone(e.target.checked)} />
          show done
        </label>
      </div>
      <Notice error={error} status={status} />
      {!items.length && !error && <p className="muted">No deadlines. Scan your inbox.</p>}
      <ul className="list">
        {items.map((d) => (
          <li key={d.id} className={`deadline ${d.done ? "is-done" : dueState(d, now)}`}>
            <label className="row">
              <input type="checkbox" checked={d.done} onChange={() => toggle(d)} />
              <span className="subject">{d.title}</span>
            </label>
            <div className="row spread small">
              <span className="due">
                {new Date(d.due_iso).toLocaleString([], {
                  weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
                })}
                {!d.done && dueState(d, now) === "overdue" && " · overdue"}
              </span>
              <span className="muted" title={d.evidence}>{d.mail_subject}</span>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
