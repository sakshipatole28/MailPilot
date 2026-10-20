import { useState } from "react";
import { api } from "../../shared/api";
import type { GeneratedEmail } from "../../shared/types";
import { GeneratedView, messageOf, Notice } from "../ui";

export function Compose() {
  const [instruction, setInstruction] = useState("");
  const [useRag, setUseRag] = useState(true);
  const [email, setEmail] = useState<GeneratedEmail | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function generate() {
    setBusy(true);
    setError("");
    try {
      setEmail(await api.compose(instruction, useRag));
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <textarea
        rows={4}
        placeholder="What should the email say? e.g. ask HR to reschedule my interview to next week"
        value={instruction}
        onChange={(e) => setInstruction(e.target.value)}
      />
      <div className="row">
        <button className="primary" onClick={generate} disabled={busy || instruction.trim().length < 3}>
          {busy ? "Writing…" : "Write email"}
        </button>
        <label className="small">
          <input type="checkbox" checked={useRag} onChange={(e) => setUseRag(e.target.checked)} />
          use my notes
        </label>
      </div>
      <Notice error={error} />
      {email && <GeneratedView email={email} onEdit={setEmail} />}
    </section>
  );
}
