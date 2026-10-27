import { type ReactNode, useEffect, useState } from "react";
import { hueFor, initials } from "../shared/format";
import type { GeneratedEmail } from "../shared/types";
import { CopyIcon } from "./icons";

export function messageOf(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

/** Errors stay until the next action; status messages fade out after a few seconds. */
export function Notice({ error, status }: { error?: string; status?: string }) {
  const [shown, setShown] = useState(status);
  useEffect(() => {
    setShown(status);
    if (!status) return;
    const timer = setTimeout(() => setShown(""), 4000);
    return () => clearTimeout(timer);
  }, [status]);
  if (error) return <div className="toast error" role="alert">{error}</div>;
  if (shown) return <div className="toast" role="status">{shown}</div>;
  return null;
}

export function Avatar({ name, email }: { name: string; email: string }) {
  const hue = hueFor(email || name);
  return (
    <span className="avatar" style={{ background: `hsl(${hue} 65% 52%)` }} aria-hidden="true">
      {initials(name, email)}
    </span>
  );
}

// Categories are user-defined, so colors come from a small palette picked by name.
function paletteIndex(name: string): number {
  let hash = 0;
  for (const ch of name) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return hash % 8;
}

export function CategoryBadge({ category }: { category: string | null }) {
  if (!category) return null;
  const cls = category === "Other" ? "cat-other" : `cat-${paletteIndex(category)}`;
  return <span className={`chip-tag ${cls}`}>{category}</span>;
}

export function priorityClass(score: number | null): string {
  if (score === null) return "p-none";
  return score >= 70 ? "p-high" : score >= 40 ? "p-mid" : "p-low";
}

export function Skeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="skeletons" aria-busy="true">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton-card">
          <span className="sk sk-avatar" />
          <div className="sk-lines"><span className="sk sk-line" /><span className="sk sk-line short" /></div>
        </div>
      ))}
    </div>
  );
}

export function EmptyState({ emoji, title, children }: { emoji: string; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <div className="empty-emoji" aria-hidden="true">{emoji}</div>
      <div className="empty-title">{title}</div>
      {children && <div className="empty-body">{children}</div>}
    </div>
  );
}

/** Editable subject/body with copy button, guardrail issues and the sources used. */
export function GeneratedView({
  email,
  onEdit,
}: {
  email: GeneratedEmail;
  onEdit: (email: GeneratedEmail) => void;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(`Subject: ${email.subject}\n\n${email.body}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="generated card">
      <input
        className="subject-input"
        value={email.subject}
        onChange={(e) => onEdit({ ...email, subject: e.target.value })}
        aria-label="Subject"
      />
      <textarea
        rows={9}
        value={email.body}
        onChange={(e) => onEdit({ ...email, body: e.target.value })}
        aria-label="Body"
      />
      {email.issues.length > 0 && (
        <div className="callout warn">
          <strong>Check before sending</strong>
          <ul>{email.issues.map((issue) => <li key={issue}>{issue}</li>)}</ul>
        </div>
      )}
      <div className="row spread">
        <button className="primary" onClick={copy}>
          <CopyIcon /> {copied ? "Copied!" : "Copy draft"}
        </button>
        <span className="muted tiny">{email.model.split("/").pop()}</span>
      </div>
      {email.sources.length > 0 && (
        <details>
          <summary>Used {email.sources.length} of your notes</summary>
          {email.sources.map((s) => (
            <div key={s.id} className="source">
              <strong>{s.title}</strong>
              <p>{s.text.length > 200 ? s.text.slice(0, 200) + "…" : s.text}</p>
            </div>
          ))}
        </details>
      )}
    </div>
  );
}
