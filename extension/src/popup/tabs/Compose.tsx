import { useState } from "react";
import { api } from "../../shared/api";
import type { GeneratedEmail } from "../../shared/types";
import { GeneratedView, messageOf, Notice } from "../ui";

const IDEAS = [
  "Ask HR to move my interview to next week",
  "Thank the recruiter after my interview",
  "Ask my professor for an extension on the project",
  "Follow up on my application status",
];

export function Compose() {
  const [instruction, setInstruction] = useState("");
  const [useRag, setUseRag] = useState(true);
  const [email, setEmail] = useState<GeneratedEmail | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function generate(text = instruction) {
    if (text.trim().length < 3) return;
    setInstruction(text);
    setBusy(true);
    setError("");
    try {
      setEmail(await api.compose(text, useRag));
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <div className="card">
        <textarea
          rows={3}
          placeholder="What do you want to say? One line is enough."
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && (e.metaKey || e.ctrlKey) && generate()}
        />
        <div className="row spread">
          <label className="toggle compact">
            <input type="checkbox" checked={useRag} onChange={(e) => setUseRag(e.target.checked)} />
            <span>Use my notes</span>
          </label>
          <button className="primary" onClick={() => generate()} disabled={busy || instruction.trim().length < 3}>
            {busy ? "Writing…" : "✨ Write email"}
          </button>
        </div>
      </div>
      <Notice error={error} />
      {email ? (
        <GeneratedView email={email} onEdit={setEmail} />
      ) : (
        <div className="examples">
          {IDEAS.map((idea) => (
            <button key={idea} className="example" onClick={() => generate(idea)} disabled={busy}>{idea}</button>
          ))}
        </div>
      )}
    </section>
  );
}
