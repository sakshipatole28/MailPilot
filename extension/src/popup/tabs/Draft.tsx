import { useEffect, useState } from "react";
import { api } from "../../shared/api";
import type { GeneratedEmail, Mail } from "../../shared/types";
import { CategoryBadge, GeneratedView, messageOf, Notice } from "../ui";

export function Draft({ mail, onChange }: { mail: Mail | null; onChange: (m: Mail) => void }) {
  const [instruction, setInstruction] = useState("");
  const [useRag, setUseRag] = useState(true);
  const [draft, setDraft] = useState<GeneratedEmail | null>(null);
  const [rated, setRated] = useState(0);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    setDraft(null);
    setRated(0);
    setStatus("");
    setError("");
    if (mail && !mail.is_read) api.updateMail(mail.id, { is_read: true }).then(onChange).catch(() => {});
  }, [mail?.id]);

  if (!mail) return <p className="muted">Pick a mail in the Inbox tab.</p>;

  async function run(task: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await task();
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(false);
    }
  }

  const generate = () =>
    run(async () => {
      setStatus("Drafting…");
      setDraft(await api.draft(mail.id, instruction, useRag));
      setRated(0);
      setStatus("");
    });

  const findDeadlines = () =>
    run(async () => {
      const found = await api.extractDeadlines(mail.id);
      setStatus(found.length ? `Deadlines: ${found.map((d) => d.title).join(", ")}` : "No deadlines found");
      chrome.runtime.sendMessage({ type: "refresh-deadlines" }).catch(() => undefined);
    });

  const markReplied = () => run(async () => onChange(await api.updateMail(mail.id, { replied: true })));

  async function rate(rating: number) {
    if (!draft?.draft_id) return;
    await api.feedback(draft.draft_id, rating);
    setRated(rating);
  }

  return (
    <section>
      <div className="mail-head">
        <div className="subject">{mail.subject}</div>
        <div className="muted small">
          {mail.sender_name} &lt;{mail.sender}&gt; · {new Date(mail.received_at).toLocaleString()}
        </div>
        <CategoryBadge category={mail.category} />
      </div>
      <details>
        <summary>Show mail</summary>
        <pre className="mail-body">{mail.body}</pre>
      </details>

      <input
        placeholder="Optional instruction, e.g. accept the Thursday slot"
        value={instruction}
        onChange={(e) => setInstruction(e.target.value)}
      />
      <div className="row">
        <button className="primary" onClick={generate} disabled={busy}>Draft reply</button>
        <button onClick={findDeadlines} disabled={busy}>Find deadlines</button>
        <button onClick={markReplied} disabled={busy || mail.replied}>
          {mail.replied ? "Replied" : "Mark replied"}
        </button>
        <label className="small">
          <input type="checkbox" checked={useRag} onChange={(e) => setUseRag(e.target.checked)} />
          use my notes
        </label>
      </div>
      <Notice error={error} status={status} />

      {draft && (
        <>
          <GeneratedView email={draft} onEdit={setDraft} />
          <div className="row small">
            Rate this draft:
            {[1, 2, 3, 4, 5].map((n) => (
              <button key={n} className={`star ${rated >= n ? "on" : ""}`} onClick={() => rate(n)}>
                {n}
              </button>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
