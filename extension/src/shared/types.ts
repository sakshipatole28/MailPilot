// Mirrors backend/app/models.py

export interface Mail {
  id: string;
  sender: string;
  sender_name: string;
  subject: string;
  body: string;
  received_at: string;
  is_read: boolean;
  replied: boolean;
  category: string | null;
  priority: string | null;
  needs_reply: boolean | null;
  classified_by: string | null; // "keywords", "llm" or "user"
  headers: Record<string, string>;
  labels: string[];
  links: string[];
  summary: string;
  intents: string[]; // reply, task, meeting, fyi
  priority_score: number | null;
  priority_reasons: string[];
  risk_level: "low" | "medium" | "high" | null;
  risk_reasons: string[];
  triage_status: "pending" | "done" | "failed" | null;
}

export interface Category {
  name: string;
  description: string;
}

export interface Classification {
  category: string;
  priority: string;
  needs_reply: boolean;
  reason: string;
  method: string;
}

export interface Deadline {
  id: number;
  mail_id: string;
  title: string;
  due_iso: string | null; // null: a to-do without a date
  confidence: number;
  evidence: string;
  done: boolean;
  mail_subject: string | null;
}

export interface SourceChunk {
  id: string;
  text: string;
  source: string;
  title: string;
  score: number;
}

export interface GeneratedEmail {
  draft_id: number | null;
  subject: string;
  body: string;
  sources: SourceChunk[];
  issues: string[];
  quick_replies: string[];
  revisions: number; // self-correction rounds
  first_pass_issues: number; // unsupported facts in the first draft
  model: string;
}

export interface BackendSettings {
  model: string;
  tone: string;
  categories: Category[];
  local_only: boolean;
  user_name: string;
  auto_triage: boolean;
  suggested_models: string[];
  presets: Record<string, Category[]>;
}

export interface Brief {
  needs_reply: Mail[];
  due_soon: Deadline[];
  suspicious: Mail[];
  unread: number;
  pending_triage: number;
}

export interface TriageStatus {
  queued: number;
  done: number;
  pending: number;
  failed: number;
  new: number;
}

export interface Citation {
  mail_id: string;
  subject: string;
  sender: string;
  received_at: string;
}

export interface AskAnswer {
  answer: string;
  citations: Citation[];
  searches: string[]; // queries the agent ran
  model: string;
}
