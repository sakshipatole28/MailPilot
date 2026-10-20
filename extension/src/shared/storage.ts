// Everything the popup remembers lives in chrome.storage.local (never synced, never sent anywhere
// except: the API key for the chosen model goes to our own backend as an X-Api-Key header).

export type Provider = "gemini" | "groq" | "openai" | "anthropic";

export interface LocalSettings {
  apiBase: string;
  model: string; // empty = use the backend default
  apiKeys: Partial<Record<Provider, string>>;
}

export const DEFAULTS: LocalSettings = {
  apiBase: "http://localhost:8000",
  model: "",
  apiKeys: {},
};

export function providerForModel(model: string): Provider | null {
  if (model.startsWith("gemini/")) return "gemini";
  if (model.startsWith("groq/")) return "groq";
  if (model.startsWith("anthropic/") || model.startsWith("claude")) return "anthropic";
  if (model.startsWith("openai/") || model.startsWith("gpt") || /^o\d/.test(model)) return "openai";
  return null; // ollama/... and unknown providers: no key
}

export function keyForModel(model: string, keys: LocalSettings["apiKeys"]): string | undefined {
  const provider = providerForModel(model);
  return provider ? keys[provider] || undefined : undefined;
}

export async function loadSettings(): Promise<LocalSettings> {
  const stored = await chrome.storage.local.get("settings");
  return { ...DEFAULTS, ...(stored.settings ?? {}) };
}

export async function saveSettings(settings: LocalSettings): Promise<void> {
  await chrome.storage.local.set({ settings });
}
