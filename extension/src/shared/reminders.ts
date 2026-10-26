// Pure functions for reminders and the badge, so they can be unit tested without Chrome.
import type { Deadline } from "./types";

const HOUR = 60 * 60 * 1000;
export const REMINDER_OFFSETS = [
  { label: "24h", ms: 24 * HOUR },
  { label: "2h", ms: 2 * HOUR },
];

export interface PlannedAlarm {
  name: string; // "dl:<deadline id>:<offset label>"
  when: number; // epoch ms
}

export function plannedAlarms(deadlines: Deadline[], now: number): PlannedAlarm[] {
  const alarms: PlannedAlarm[] = [];
  for (const d of deadlines) {
    if (d.done || !d.due_iso) continue; // undated to-dos get no reminders
    const due = Date.parse(d.due_iso);
    for (const offset of REMINDER_OFFSETS) {
      const when = due - offset.ms;
      if (when > now) alarms.push({ name: `dl:${d.id}:${offset.label}`, when });
    }
  }
  return alarms;
}

export function parseAlarmName(name: string): { id: number; label: string } | null {
  const match = /^dl:(\d+):(\w+)$/.exec(name);
  return match ? { id: Number(match[1]), label: match[2] } : null;
}

function sameLocalDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

export function dueTodayCount(deadlines: Deadline[], now: Date): number {
  return deadlines.filter((d) => !d.done && d.due_iso && sameLocalDay(new Date(d.due_iso), now))
    .length;
}

export type DueState = "overdue" | "today" | "upcoming" | "undated";

export function dueState(d: Deadline, now: Date): DueState {
  if (!d.due_iso) return "undated";
  const due = new Date(d.due_iso);
  if (due.getTime() < now.getTime()) return "overdue";
  return sameLocalDay(due, now) ? "today" : "upcoming";
}
