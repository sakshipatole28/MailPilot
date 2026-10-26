// Inbox views (like a split inbox), sorting and small helpers, kept pure so they can be tested.
import type { Mail } from "./types";

export type View = "all" | "reply" | "tasks" | "meetings" | "important" | "suspicious";

export const VIEWS: { id: View; label: string }[] = [
  { id: "all", label: "All" },
  { id: "reply", label: "Needs reply" },
  { id: "tasks", label: "Tasks" },
  { id: "meetings", label: "Meetings" },
  { id: "important", label: "Important" },
  { id: "suspicious", label: "Suspicious" },
];

export function inView(mail: Mail, view: View): boolean {
  switch (view) {
    case "reply":
      return Boolean(mail.needs_reply) && !mail.replied;
    case "tasks":
      return mail.intents.includes("task");
    case "meetings":
      return mail.intents.includes("meeting");
    case "important":
      return (mail.priority_score ?? 0) >= 70;
    case "suspicious":
      return mail.risk_level === "high" || mail.risk_level === "medium";
    default:
      return true;
  }
}

export type SortBy = "priority" | "newest";

export function sortMails(mails: Mail[], by: SortBy): Mail[] {
  const newest = (a: Mail, b: Mail) => Date.parse(b.received_at) - Date.parse(a.received_at);
  if (by === "newest") return [...mails].sort(newest);
  // Untriaged mail (no score yet) sorts after triaged mail, newest first within ties.
  return [...mails].sort((a, b) => (b.priority_score ?? -1) - (a.priority_score ?? -1) || newest(a, b));
}

/** The https link from a List-Unsubscribe header ("<mailto:...>, <https://...>"), if any. */
export function unsubscribeUrl(mail: Mail): string | null {
  const header = mail.headers?.list_unsubscribe ?? "";
  const match = header.match(/<(https:\/\/[^>]+)>/i);
  return match ? match[1] : null;
}

export function scoreClass(score: number | null): string {
  if (score === null) return "score none";
  return score >= 70 ? "score high" : score >= 40 ? "score mid" : "score low";
}
