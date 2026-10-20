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
  classified_by: string | null;
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
  due_iso: string;
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
  model: string;
}

export interface BackendSettings {
  model: string;
  tone: string;
  categories: string[];
  local_only: boolean;
  user_name: string;
  suggested_models: string[];
}
