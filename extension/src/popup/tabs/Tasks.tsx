import { useEffect, useState } from "react";
import { api, apiUrl } from "../../shared/api";
import { dueLabel } from "../../shared/format";
import { dueState } from "../../shared/reminders";
import type { Deadline } from "../../shared/types";
import { CalendarIcon, CheckIcon } from "../icons";
import { EmptyState, messageOf, Notice, Skeleton } from "../ui";

function refreshBackground() {
  chrome.runtime.sendMessage({ type: "refresh-deadlines" }).catch(() => undefined);
}

function TaskRow({ task, now, onToggle }: { task: Deadline; now: Date; onToggle: () => void }) {
  const state = task.done ? "is-done" : dueState(task, now);
  return (
    <li className={`task ${state}`}>
      <button className={`check ${task.done ? "on" : ""}`} onClick={onToggle} aria-label={task.done ? "Mark not done" : "Mark done"}>
        {task.done && <CheckIcon />}
      </button>
      <div className="grow">
        <div className="task-title">{task.title}</div>
        <div className="task-meta">
          {task.due_iso && <span className="due">{state === "overdue" ? "Overdue · " : ""}{dueLabel(task.due_iso, now)}</span>}
          {task.mail_subject && <span className="muted" title={task.evidence}>from "{task.mail_subject}"</span>}
        </div>
      </div>
    </li>
  );
}

export function Tasks() {
  const [items, setItems] = useState<Deadline[] | null>(null);
  const [showDone, setShowDone] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    try {
      setItems(await api.deadlines(showDone));
    } catch (e) {
      setError(messageOf(e));
      setItems([]);
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
  const list = items ?? [];
  const overdue = list.filter((d) => !d.done && dueState(d, now) === "overdue");
  const upcoming = list.filter((d) => d.due_iso && (d.done || dueState(d, now) !== "overdue"));
  const undated = list.filter((d) => !d.due_iso);
  const section = (title: string, rows: Deadline[]) =>
    rows.length > 0 && (
      <>
        <h3>{title} <span className="count">{rows.length}</span></h3>
        <ul className="task-list">{rows.map((d) => <TaskRow key={d.id} task={d} now={now} onToggle={() => toggle(d)} />)}</ul>
      </>
    );

  return (
    <section>
      <div className="row spread">
        <button onClick={exportCalendar} disabled={!list.some((d) => d.due_iso)}><CalendarIcon /> Add to calendar</button>
        <label className="toggle compact">
          <input type="checkbox" checked={showDone} onChange={(e) => setShowDone(e.target.checked)} />
          <span>Show done</span>
        </label>
      </div>
      <Notice error={error} />
      {items === null ? <Skeleton rows={4} /> : !list.length ? (
        <EmptyState emoji="✅" title="No tasks">
          Deadlines and to-dos appear here as MailPilot reads your mail. You get a reminder 24 h and 2 h before each one.
        </EmptyState>
      ) : (
        <>
          {section("Coming up", upcoming)}
          {section("No date", undated)}
          {overdue.length > 0 && (
            <details className="overdue-group" open={overdue.length <= 3}>
              <summary>Overdue <span className="count">{overdue.length}</span></summary>
              <ul className="task-list">
                {overdue.map((d) => <TaskRow key={d.id} task={d} now={now} onToggle={() => toggle(d)} />)}
              </ul>
            </details>
          )}
        </>
      )}
    </section>
  );
}
