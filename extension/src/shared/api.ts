import { keyForModel, loadSettings } from "./storage";
import type {
  BackendSettings,
  Classification,
  Deadline,
  GeneratedEmail,
  Mail,
} from "./types";

async function request<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const settings = await loadSettings();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (settings.model) headers["X-Model"] = settings.model;
  const key = keyForModel(settings.model, settings.apiKeys);
  if (key) headers["X-Api-Key"] = key;

  let res: Response;
  try {
    res = await fetch(settings.apiBase + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error(`Backend not reachable at ${settings.apiBase}. Is it running?`);
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    throw new Error(detail || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

export const api = {
  sync: () => request<{ fetched: number; new: number }>("/mail/sync", "POST"),
  mails: () => request<Mail[]>("/mail"),
  updateMail: (id: string, update: { is_read?: boolean; replied?: boolean }) =>
    request<Mail>(`/mail/${encodeURIComponent(id)}`, "PATCH", update),
  classify: (mailId: string) => request<Classification>("/classify", "POST", { mail_id: mailId }),

  deadlines: (includeDone = false) =>
    request<Deadline[]>(`/deadlines?include_done=${includeDone}`),
  extractDeadlines: (mailId: string) =>
    request<Deadline[]>("/deadlines/extract", "POST", { mail_id: mailId }),
  setDeadlineDone: (id: number, done: boolean) => request(`/deadlines/${id}`, "PATCH", { done }),

  draft: (mailId: string, instruction: string, useRag: boolean) =>
    request<GeneratedEmail>("/draft", "POST", {
      mail_id: mailId,
      instruction,
      use_rag: useRag,
    }),
  compose: (instruction: string, useRag: boolean) =>
    request<GeneratedEmail>("/compose", "POST", { instruction, use_rag: useRag }),
  feedback: (draftId: number, rating: number) =>
    request(`/drafts/${draftId}/feedback`, "POST", { rating }),

  ingest: () => request<{ files: number; chunks: number }>("/rag/ingest", "POST"),
  settings: () => request<BackendSettings>("/settings"),
  saveSettings: (update: Partial<BackendSettings>) =>
    request<BackendSettings>("/settings", "POST", update),
};
