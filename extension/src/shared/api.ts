import { keyForModel, loadSettings } from "./storage";
import type {
  AskAnswer,
  BackendSettings,
  Brief,
  Classification,
  Deadline,
  GeneratedEmail,
  Mail,
  TriageStatus,
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

export async function apiUrl(path: string): Promise<string> {
  return (await loadSettings()).apiBase + path;
}

export const api = {
  sync: () => request<{ fetched: number; new: number; queued: number }>("/mail/sync", "POST"),
  mails: () => request<Mail[]>("/mail"),
  updateMail: (id: string, update: { is_read?: boolean; replied?: boolean; category?: string }) =>
    request<Mail>(`/mail/${encodeURIComponent(id)}`, "PATCH", update),
  classify: (mailId: string) => request<Classification>("/classify", "POST", { mail_id: mailId }),
  triage: (limit = 10) =>
    request<{ triaged: number; failed: string[]; remaining: number }>("/triage", "POST", { limit }),
  triageStatus: () => request<TriageStatus>("/triage/status"),
  brief: () => request<Brief>("/brief"),
  ask: (question: string) => request<AskAnswer>("/ask", "POST", { question }),

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
