import { useState } from "react";
import type { GeneratedEmail } from "../shared/types";

export function Notice({ error, status }: { error?: string; status?: string }) {
  if (error) return <div className="notice error">{error}</div>;
  if (status) return <div className="notice">{status}</div>;
  return null;
}

export function CategoryBadge({ category }: { category: string | null }) {
  if (!category) return null;
  return <span className={`badge cat-${category.replace(/[^a-z]/gi, "")}`}>{category}</span>;
}

export function messageOf(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
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
    <div className="generated">
      <input
        value={email.subject}
        onChange={(e) => onEdit({ ...email, subject: e.target.value })}
        aria-label="Subject"
      />
      <textarea
        rows={10}
        value={email.body}
        onChange={(e) => onEdit({ ...email, body: e.target.value })}
        aria-label="Body"
      />
      <div className="row">
        <button className="primary" onClick={copy}>
          {copied ? "Copied" : "Copy"}
        </button>
        <span className="muted">{email.model}</span>
      </div>
      {email.issues.length > 0 && (
        <div className="notice warn">
          <strong>Check before sending:</strong>
          <ul>
            {email.issues.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        </div>
      )}
      {email.sources.length > 0 && (
        <details>
          <summary>Sources used ({email.sources.length})</summary>
          {email.sources.map((s) => (
            <div key={s.id} className="source">
              <strong>{s.title}</strong> <span className="muted">{s.source}</span>
              <p>{s.text.length > 220 ? s.text.slice(0, 220) + "…" : s.text}</p>
            </div>
          ))}
        </details>
      )}
    </div>
  );
}
