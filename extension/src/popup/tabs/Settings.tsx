import { useEffect, useState } from "react";
import { api } from "../../shared/api";
import { DEFAULTS, loadSettings, type LocalSettings, type Provider, saveSettings } from "../../shared/storage";
import type { BackendSettings } from "../../shared/types";
import { messageOf, Notice } from "../ui";

const PROVIDERS: { id: Provider; label: string }[] = [
  { id: "gemini", label: "Gemini API key (free tier)" },
  { id: "groq", label: "Groq API key (free tier)" },
  { id: "openai", label: "OpenAI API key" },
  { id: "anthropic", label: "Anthropic API key" },
];

export function Settings() {
  const [local, setLocal] = useState<LocalSettings>(DEFAULTS);
  const [backend, setBackend] = useState<BackendSettings | null>(null);
  const [categories, setCategories] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    loadSettings().then(setLocal);
    api
      .settings()
      .then((s) => {
        setBackend(s);
        setCategories(s.categories.join(", "));
      })
      .catch((e) => setError(messageOf(e)));
  }, []);

  async function save() {
    setError("");
    try {
      await saveSettings(local);
      if (backend) {
        const saved = await api.saveSettings({
          model: local.model || backend.model,
          tone: backend.tone,
          user_name: backend.user_name,
          local_only: backend.local_only,
          categories: categories.split(",").map((c) => c.trim()).filter(Boolean),
        });
        setBackend(saved);
      }
      setStatus("Saved");
    } catch (e) {
      setError(messageOf(e));
    }
  }

  async function reindex() {
    try {
      const r = await api.ingest();
      setStatus(`Indexed ${r.chunks} chunks from ${r.files} files`);
    } catch (e) {
      setError(messageOf(e));
    }
  }

  const model = local.model || backend?.model || "";
  return (
    <section className="form">
      <label>
        Backend URL
        <input value={local.apiBase} onChange={(e) => setLocal({ ...local, apiBase: e.target.value })} />
      </label>
      <label>
        Model
        <input
          list="models"
          value={model}
          onChange={(e) => setLocal({ ...local, model: e.target.value })}
        />
        <datalist id="models">
          {backend?.suggested_models.map((m) => <option key={m} value={m} />)}
        </datalist>
      </label>
      {PROVIDERS.map((p) => (
        <label key={p.id}>
          {p.label}
          <input
            type="password"
            autoComplete="off"
            value={local.apiKeys[p.id] ?? ""}
            onChange={(e) => setLocal({ ...local, apiKeys: { ...local.apiKeys, [p.id]: e.target.value } })}
          />
        </label>
      ))}
      <p className="muted small">
        Keys stay in this browser (chrome.storage.local) and are sent only to your backend, per request.
        Leave empty to use the keys in the backend's .env.
      </p>
      {backend && (
        <>
          <label>
            Your name (sign-off)
            <input value={backend.user_name} onChange={(e) => setBackend({ ...backend, user_name: e.target.value })} />
          </label>
          <label>
            Tone
            <input value={backend.tone} onChange={(e) => setBackend({ ...backend, tone: e.target.value })} />
          </label>
          <label>
            Categories (comma separated)
            <input value={categories} onChange={(e) => setCategories(e.target.value)} />
          </label>
          <label className="row">
            <input
              type="checkbox"
              checked={backend.local_only}
              onChange={(e) => setBackend({ ...backend, local_only: e.target.checked })}
            />
            Local only (allow only ollama/ models)
          </label>
        </>
      )}
      <div className="row">
        <button className="primary" onClick={save}>Save</button>
        <button onClick={reindex}>Re-index my notes</button>
      </div>
      <Notice error={error} status={status} />
    </section>
  );
}
