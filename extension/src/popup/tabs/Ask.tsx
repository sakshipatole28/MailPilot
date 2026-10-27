import { useState } from "react";
import { api } from "../../shared/api";
import { timeAgo } from "../../shared/format";
import type { AskAnswer, Mail } from "../../shared/types";
import { AskIcon } from "../icons";
import { EmptyState, messageOf, Notice } from "../ui";

const EXAMPLES = [
  "When is my next interview?",
  "What do I have to pay this month?",
  "Did anyone send me a link I need to open?",
  "What did my professor ask for?",
];

export function Ask({ onOpen }: { onOpen: (mail: Mail) => void }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AskAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function ask(q: string) {
    if (q.trim().length < 3) return;
    setQuestion(q);
    setBusy(true);
    setError("");
    setAnswer(null);
    try {
      setAnswer(await api.ask(q.trim()));
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(false);
    }
  }

  async function open(mailId: string) {
    const mail = (await api.mails()).find((m) => m.id === mailId);
    if (mail) onOpen(mail);
  }

  return (
    <section>
      <form className="ask-box" onSubmit={(e) => { e.preventDefault(); ask(question); }}>
        <input
          placeholder="Ask anything about your mail…"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          autoFocus
        />
        <button className="primary" disabled={busy || question.trim().length < 3}>{busy ? "…" : "Ask"}</button>
      </form>

      <Notice error={error} />
      {busy && (
        <div className="thinking"><span className="dot" /><span className="dot" /><span className="dot" /> Searching your inbox</div>
      )}

      {answer && (
        <div className="card answer">
          <p>{answer.answer}</p>
          {answer.searches.length > 1 && (
            <p className="muted tiny">Searched: {answer.searches.map((q) => `"${q}"`).join(" → ")}</p>
          )}
          {answer.citations.length > 0 && (
            <>
              <h3>From these mails</h3>
              <ul className="cites">
                {answer.citations.map((c) => (
                  <li key={c.mail_id} onClick={() => open(c.mail_id)}>
                    <div className="subject">{c.subject}</div>
                    <div className="muted tiny">{c.sender} · {timeAgo(c.received_at)}</div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {!answer && !busy && (
        <>
          <EmptyState emoji="🔎" title="Ask your inbox">
            Answers come only from your mail, with links to the mails they used.
          </EmptyState>
          <div className="examples">
            {EXAMPLES.map((q) => (
              <button key={q} className="example" onClick={() => ask(q)}><AskIcon /> {q}</button>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
