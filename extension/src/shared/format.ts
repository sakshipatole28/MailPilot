// Small display helpers, kept pure so they can be tested.

/** "now", "5m", "3h", "2d", or a short date for anything older than a week. */
export function timeAgo(iso: string, now: Date = new Date()): string {
  const seconds = Math.max(0, (now.getTime() - Date.parse(iso)) / 1000);
  if (seconds < 60) return "now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  if (seconds < 7 * 86400) return `${Math.floor(seconds / 86400)}d`;
  return new Date(iso).toLocaleDateString([], { day: "numeric", month: "short" });
}

/** "Priya Nair" -> "PN", "tpo@westbrook.edu" -> "T". */
export function initials(name: string, email = ""): string {
  const words = (name || email.split("@")[0]).replace(/[^\p{L}\p{N} ]/gu, " ").trim().split(/\s+/);
  const letters = words.length > 1 ? words[0][0] + words[words.length - 1][0] : (words[0] ?? "?")[0];
  return (letters ?? "?").toUpperCase();
}

/** A stable hue (0-359) for a sender, so each person keeps the same avatar color. */
export function hueFor(text: string): number {
  let hash = 0;
  for (const ch of text) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return hash % 360;
}

/** "Tue 21 Oct, 11:59 PM" style due label, "Today 6:00 PM" or "Tomorrow …" when close. */
export function dueLabel(iso: string, now: Date = new Date()): string {
  const due = new Date(iso);
  const time = due.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const days = Math.round(
    (new Date(due.getFullYear(), due.getMonth(), due.getDate()).getTime() -
      new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()) / 86400000,
  );
  if (days === 0) return `Today ${time}`;
  if (days === 1) return `Tomorrow ${time}`;
  if (days === -1) return `Yesterday ${time}`;
  return `${due.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" })}, ${time}`;
}

/** Case-insensitive search over the fields a person would type. */
export function matchesSearch(
  mail: { subject: string; sender: string; sender_name: string; summary: string },
  query: string,
): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return [mail.subject, mail.sender, mail.sender_name, mail.summary].some((f) => f.toLowerCase().includes(q));
}
