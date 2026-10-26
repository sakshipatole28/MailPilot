import { useEffect, useState } from "react";
import { api, apiUrl } from "../../shared/api";
import { dueState } from "../../shared/reminders";
import type { Deadline } from "../../shared/types";
import { messageOf, Notice } from "../ui";

function refreshBackground() {
  chrome.runtime.sendMessage({ type: "refresh-deadlines" }).catch(() => undefined);
}

function TaskRow({ task, now, onToggle }: { task: Deadline; now: Date; onToggle: () => void }) {
  const state = task.done ? "is-done" : dueState(task, now);
  return (
    <li className={`deadline ${state}`}>
      <label className="row">
        <input type="checkbox" checked={task.done} onChange={onToggle} />
        <span className="subject">{task.title}</span>
      </label>
      <div className="row spread small">
        <span className="due">
          {task.due_iso
            ? new Date(task.due_iso).toLocaleString([], {
                weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
              })
            : "No date"}
          {state === "overdue" && " · overdue"}
        </span>
        <span className="muted" title={task.evidence}>{task.mail_subject}</span>
      </div>
    </li>
  );
}

export function Tasks() {
  const [items, setItems] = useState<Deadline[]>([]);
  const [showDone, setShowDone] = useState(false);
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

  async function toggle(d: Deadline) {
    await api.setDeadlineDone(d.id, !d.done);
    await load();
    refreshBackground();
  }

  // Downloads an .ics file that Google Calendar, Outlook or Apple Calendar can import.
  async function exportCalendar() {
    chrome.tabs.create({ url: await apiUrl("/deadlines.ics") });
  }

  const now = new Date();
  const dated = items.filter((d) => d.due_iso);
  const undated = items.filter((d) => !d.due_iso);
  return (
    <section>
      <div className="row">
        <button onClick={exportCalendar} disabled={!dated.length}>Export to calendar</button>
        <label className="small">
          <input type="checkbox" checked={showDone} onChange={(e) => setShowDone(e.target.checked)} />
          show done
        </label>
      </div>
      <p className="muted small">
        Tasks are found automatically when mail is triaged. You get reminders 24 h and 2 h before
        each deadline.
      </p>
      <Notice error={error} />
      {!items.length && !error && <p className="muted">No tasks yet.</p>}
      {dated.length > 0 && <h3>Deadlines</h3>}
      <ul className="list">
        {dated.map((d) => <TaskRow key={d.id} task={d} now={now} onToggle={() => toggle(d)} />)}
      </ul>
      {undated.length > 0 && <h3>To-do</h3>}
      <ul className="list">
        {undated.map((d) => <TaskRow key={d.id} task={d} now={now} onToggle={() => toggle(d)} />)}
      </ul>
    </section>
  );
}
