import { useEffect, useState } from "react";
import { api } from "../../shared/api";
import { DEFAULTS, loadSettings, type LocalSettings, type Provider, saveSettings } from "../../shared/storage";
import type { BackendSettings, Category } from "../../shared/types";
import { messageOf, Notice } from "../ui";

const PROVIDERS: { id: Provider; label: string }[] = [
  { id: "groq", label: "Groq API key (free tier)" },
  { id: "gemini", label: "Gemini API key (free tier)" },
  { id: "openai", label: "OpenAI API key" },
  { id: "anthropic", label: "Anthropic API key" },
];

function CategoryEditor({
  categories,
  presets,
  onChange,
}: {
  categories: Category[];
  presets: Record<string, Category[]>;
  onChange: (c: Category[]) => void;
}) {
  const update = (i: number, patch: Partial<Category>) =>
    onChange(categories.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  return (
    <fieldset>
      <legend>Categories</legend>
      <p className="muted small">
        Describe each category in plain words; the AI reads the description. Corrections you make
        in the Draft tab teach it too.
      </p>
      <div className="row">
        Presets:
        {Object.keys(presets).map((name) => (
          <button key={name} onClick={() => onChange(presets[name])}>{name}</button>
        ))}
      </div>
      {categories.map((c, i) => (
        <div key={i} className="category-row">
          <input value={c.name} onChange={(e) => update(i, { name: e.target.value })} aria-label="Name" />
          <input
            value={c.description}
            placeholder="What belongs here, e.g. anything from my landlord"
            onChange={(e) => update(i, { description: e.target.value })}
            aria-label="Description"
          />
          <button onClick={() => onChange(categories.filter((_, j) => j !== i))} aria-label="Remove">×</button>
        </div>
      ))}
      <button onClick={() => onChange([...categories, { name: "", description: "" }])}>Add category</button>
    </fieldset>
  );
}

export function Settings() {
  const [local, setLocal] = useState<LocalSettings>(DEFAULTS);
  const [backend, setBackend] = useState<BackendSettings | null>(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    loadSettings().then(setLocal);
    api.settings().then(setBackend).catch((e) => setError(messageOf(e)));
  }, []);

  async function save() {
    setError("");
    try {
      await saveSettings(local);
      if (backend) {
        const categories = backend.categories.filter((c) => c.name.trim());
        setBackend(await api.saveSettings({
          model: local.model || backend.model,
          tone: backend.tone,
          user_name: backend.user_name,
          local_only: backend.local_only,
          auto_triage: backend.auto_triage,
          categories,
        }));
      }
      setStatus("Saved. New mail uses these settings.");
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
        Model
        <input list="models" value={model} onChange={(e) => setLocal({ ...local, model: e.target.value })} />
        <datalist id="models">
          {backend?.suggested_models.map((m) => <option key={m} value={m} />)}
        </datalist>
      </label>
      {backend && (
        <>
          <label className="row">
            <input
              type="checkbox"
              checked={backend.auto_triage}
              onChange={(e) => setBackend({ ...backend, auto_triage: e.target.checked })}
            />
            Triage new mail automatically (uses the backend's API key)
          </label>
          <label className="row">
            <input
              type="checkbox"
              checked={backend.local_only}
              onChange={(e) => setBackend({ ...backend, local_only: e.target.checked })}
            />
            Local only (allow only ollama/ models)
          </label>
          <label>
            Your name (sign-off)
            <input value={backend.user_name} onChange={(e) => setBackend({ ...backend, user_name: e.target.value })} />
          </label>
          <label>
            Tone
            <input value={backend.tone} onChange={(e) => setBackend({ ...backend, tone: e.target.value })} />
          </label>
          <CategoryEditor
            categories={backend.categories}
            presets={backend.presets}
            onChange={(categories) => setBackend({ ...backend, categories })}
          />
        </>
      )}
      <details>
        <summary>API keys and backend</summary>
        <label>
          Backend URL
          <input value={local.apiBase} onChange={(e) => setLocal({ ...local, apiBase: e.target.value })} />
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
          Keys stay in this browser and are sent only to your backend, per request. Leave empty to
          use the keys in the backend's .env (needed for background triage).
        </p>
      </details>
      <div className="row">
        <button className="primary" onClick={save}>Save</button>
        <button onClick={reindex}>Re-index my notes</button>
      </div>
      <Notice error={error} status={status} />
    </section>
  );
}
