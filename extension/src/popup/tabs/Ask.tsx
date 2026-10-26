import { useState } from "react";
import { api } from "../../shared/api";
import type { AskAnswer, Mail } from "../../shared/types";
import { messageOf, Notice } from "../ui";

const EXAMPLES = [
  "When is my next interview?",
  "What do I have to pay this month?",
  "Did anyone send me a link I need to open?",
];

export function Ask({ onOpen }: { onOpen: (mail: Mail) => void }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AskAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function ask(q: string) {
    setQuestion(q);
    setBusy(true);
    setError("");
    try {
      setAnswer(await api.ask(q));
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
      <form
        className="row"
        onSubmit={(e) => {
          e.preventDefault();
          if (question.trim().length >= 3) ask(question.trim());
        }}
      >
        <input
          placeholder="Ask your inbox anything…"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <button className="primary" disabled={busy || question.trim().length < 3}>
          {busy ? "Searching…" : "Ask"}
        </button>
      </form>
      <div className="chips">
        {EXAMPLES.map((q) => (
          <button key={q} className="chip" onClick={() => ask(q)} disabled={busy}>{q}</button>
        ))}
      </div>
      <Notice error={error} />
      {answer && (
        <div className="answer">
          <p>{answer.answer}</p>
          {answer.searches.length > 1 && (
            <p className="muted small">Searched: {answer.searches.map((q) => `"${q}"`).join(" → ")}</p>
          )}
          {answer.citations.length > 0 && (
            <>
              <h3>Sources</h3>
              <ul className="list">
                {answer.citations.map((c) => (
                  <li key={c.mail_id} onClick={() => open(c.mail_id)}>
                    <div className="subject">{c.subject}</div>
                    <div className="muted small">
                      {c.sender} · {new Date(c.received_at).toLocaleDateString()}
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </section>
  );
}
