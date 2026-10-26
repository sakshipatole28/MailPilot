"""SQLite storage: mails, deadlines, drafts, feedback, settings, LLM cache."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from app.config import settings
from app.models import Classification, Deadline, Feedback, GeneratedEmail, Mail

SCHEMA = """
CREATE TABLE IF NOT EXISTS mails (
    id TEXT PRIMARY KEY,
    thread_id TEXT,
    sender TEXT NOT NULL,
    sender_name TEXT DEFAULT '',
    to_addr TEXT DEFAULT '',
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    received_at TEXT NOT NULL,
    is_read INTEGER DEFAULT 0,
    replied INTEGER DEFAULT 0,
    category TEXT,
    priority TEXT,
    needs_reply INTEGER,
    classified_by TEXT
);
CREATE TABLE IF NOT EXISTS deadlines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mail_id TEXT NOT NULL,
    title TEXT NOT NULL,
    due_iso TEXT NOT NULL,
    confidence REAL DEFAULT 0,
    evidence TEXT DEFAULT '',
    done INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE (mail_id, title, due_iso)
);
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mail_id TEXT,
    instruction TEXT DEFAULT '',
    subject TEXT DEFAULT '',
    body TEXT NOT NULL,
    sources_json TEXT DEFAULT '[]',
    issues_json TEXT DEFAULT '[]',
    model TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id INTEGER NOT NULL,
    rating INTEGER NOT NULL,
    comment TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS llm_cache (
    key TEXT PRIMARY KEY,
    response TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

# Columns added after the first release. init_db() adds any that an existing database lacks,
# so upgrading never needs a manual migration and never loses data.
MAIL_COLUMNS = {
    "headers_json": "TEXT DEFAULT '{}'",
    "labels_json": "TEXT DEFAULT '[]'",
    "links_json": "TEXT DEFAULT '[]'",
    "summary": "TEXT DEFAULT ''",
    "intents_json": "TEXT DEFAULT '[]'",
    "priority_score": "INTEGER",
    "priority_reasons_json": "TEXT DEFAULT '[]'",
    "risk_level": "TEXT",
    "risk_reasons_json": "TEXT DEFAULT '[]'",
    "triage_status": "TEXT",
    "triage_error": "TEXT DEFAULT ''",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def get_conn():
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(mails)")}
        for column, ddl in MAIL_COLUMNS.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE mails ADD COLUMN {column} {ddl}")


# ---- settings (key/value, JSON-encoded) ----

def get_setting(key: str, default=None):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def set_setting(key: str, value) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )


# ---- llm cache ----

def cache_get(key: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute("SELECT response FROM llm_cache WHERE key = ?", (key,)).fetchone()
    return row["response"] if row else None


def cache_put(key: str, response: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO llm_cache (key, response, created_at) VALUES (?, ?, ?)",
            (key, response, now_iso()),
        )


# ---- mails ----

def _row_to_mail(row: sqlite3.Row) -> Mail:
    needs_reply = row["needs_reply"]
    return Mail(
        id=row["id"], thread_id=row["thread_id"], sender=row["sender"],
        sender_name=row["sender_name"], to=row["to_addr"], subject=row["subject"],
        body=row["body"], received_at=row["received_at"], is_read=bool(row["is_read"]),
        replied=bool(row["replied"]), category=row["category"], priority=row["priority"],
        needs_reply=None if needs_reply is None else bool(needs_reply),
        classified_by=row["classified_by"],
        headers=json.loads(row["headers_json"] or "{}"),
        labels=json.loads(row["labels_json"] or "[]"),
        links=json.loads(row["links_json"] or "[]"),
        summary=row["summary"] or "",
        intents=json.loads(row["intents_json"] or "[]"),
        priority_score=row["priority_score"],
        priority_reasons=json.loads(row["priority_reasons_json"] or "[]"),
        risk_level=row["risk_level"],
        risk_reasons=json.loads(row["risk_reasons_json"] or "[]"),
        triage_status=row["triage_status"],
    )


def upsert_mails(mails: list[Mail]) -> int:
    """Insert new mails, refresh read/replied flags of known ones. Returns how many were new."""
    new = 0
    with get_conn() as conn:
        for m in mails:
            cur = conn.execute(
                "INSERT OR IGNORE INTO mails (id, thread_id, sender, sender_name, to_addr, subject, "
                "body, received_at, is_read, replied, headers_json, labels_json, links_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (m.id, m.thread_id, m.sender, m.sender_name, m.to, m.subject, m.body,
                 m.received_at.isoformat(), int(m.is_read), int(m.replied),
                 json.dumps(m.headers), json.dumps(m.labels), json.dumps(m.links)),
            )
            if cur.rowcount:
                new += 1
            else:
                conn.execute("UPDATE mails SET is_read = MAX(is_read, ?) WHERE id = ?",
                             (int(m.is_read), m.id))
    return new


def get_mail(mail_id: str) -> Mail | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM mails WHERE id = ?", (mail_id,)).fetchone()
    return _row_to_mail(row) if row else None


def list_mails(category: str | None = None) -> list[Mail]:
    sql, args = "SELECT * FROM mails", ()
    if category:
        sql, args = sql + " WHERE category = ?", (category,)
    with get_conn() as conn:
        rows = conn.execute(sql + " ORDER BY received_at DESC", args).fetchall()
    return [_row_to_mail(r) for r in rows]


def get_mails(mail_ids: list[str]) -> list[Mail]:
    if not mail_ids:
        return []
    marks = ",".join("?" * len(mail_ids))
    with get_conn() as conn:
        rows = conn.execute(f"SELECT * FROM mails WHERE id IN ({marks})", mail_ids).fetchall()
    by_id = {r["id"]: _row_to_mail(r) for r in rows}
    return [by_id[i] for i in mail_ids if i in by_id]


def update_mail_flags(mail_id: str, is_read: bool | None, replied: bool | None) -> None:
    with get_conn() as conn:
        if is_read is not None:
            conn.execute("UPDATE mails SET is_read = ? WHERE id = ?", (int(is_read), mail_id))
        if replied is not None:
            conn.execute("UPDATE mails SET replied = ? WHERE id = ?", (int(replied), mail_id))


def save_classification(mail_id: str, c: Classification) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE mails SET category = ?, priority = ?, needs_reply = ?, classified_by = ? "
            "WHERE id = ?",
            (c.category, c.priority, int(c.needs_reply), c.method, mail_id),
        )


def set_user_category(mail_id: str, category: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE mails SET category = ?, classified_by = 'user' WHERE id = ?",
                     (category, mail_id))


def corrected_mails(limit: int = 200) -> list[Mail]:
    """Mails whose category the user fixed by hand: few-shot examples for the triage prompt."""
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM mails WHERE classified_by = 'user' "
                            "ORDER BY received_at DESC LIMIT ?", (limit,)).fetchall()
    return [_row_to_mail(r) for r in rows]


def replied_senders() -> set[str]:
    """Senders the user has replied to before: a strong importance signal (Gmail Priority Inbox)."""
    with get_conn() as conn:
        rows = conn.execute("SELECT DISTINCT sender FROM mails WHERE replied = 1").fetchall()
    return {r["sender"] for r in rows}


# ---- triage ----

def set_triage_status(mail_ids: list[str], status: str | None, error: str = "") -> None:
    with get_conn() as conn:
        conn.executemany("UPDATE mails SET triage_status = ?, triage_error = ? WHERE id = ?",
                         [(status, error[:300], i) for i in mail_ids])


def untriaged_mail_ids(limit: int = 1000) -> list[str]:
    """Mails never triaged (or that failed), newest first."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id FROM mails WHERE triage_status IS NULL OR triage_status = 'failed' "
            "ORDER BY received_at DESC LIMIT ?", (limit,)).fetchall()
    return [r["id"] for r in rows]


def triage_counts() -> dict[str, int]:
    with get_conn() as conn:
        rows = conn.execute("SELECT COALESCE(triage_status, 'new') AS s, COUNT(*) AS n "
                            "FROM mails GROUP BY s").fetchall()
    return {r["s"]: r["n"] for r in rows}


def save_triage(mail: Mail) -> None:
    """Store the triage fields of `mail`. A user's category correction is never overwritten."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE mails SET category = CASE WHEN classified_by = 'user' THEN category ELSE ? END, "
            "classified_by = CASE WHEN classified_by = 'user' THEN 'user' ELSE 'llm' END, "
            "priority = ?, needs_reply = ?, summary = ?, intents_json = ?, priority_score = ?, "
            "priority_reasons_json = ?, risk_level = ?, risk_reasons_json = ?, "
            "triage_status = 'done', triage_error = '' WHERE id = ?",
            (mail.category, mail.priority, int(bool(mail.needs_reply)), mail.summary,
             json.dumps(mail.intents), mail.priority_score, json.dumps(mail.priority_reasons),
             mail.risk_level, json.dumps(mail.risk_reasons), mail.id),
        )


# ---- deadlines (tasks) ----

def save_deadlines(items: list[Deadline]) -> None:
    with get_conn() as conn:
        for d in items:
            conn.execute(
                "INSERT OR IGNORE INTO deadlines (mail_id, title, due_iso, confidence, evidence, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (d.mail_id, d.title, d.due_iso or "", d.confidence, d.evidence, now_iso()),
            )


def list_deadlines(include_done: bool = False, mail_id: str | None = None) -> list[Deadline]:
    sql = ("SELECT d.*, m.subject AS mail_subject FROM deadlines d "
           "LEFT JOIN mails m ON m.id = d.mail_id WHERE 1 = 1")
    args: list = []
    if not include_done:
        sql += " AND d.done = 0"
    if mail_id:
        sql += " AND d.mail_id = ?"
        args.append(mail_id)
    with get_conn() as conn:
        rows = conn.execute(sql, args).fetchall()
    items = [Deadline(id=r["id"], mail_id=r["mail_id"], title=r["title"],
                      due_iso=r["due_iso"] or None,  # stored as '' when the task has no date
                      confidence=r["confidence"], evidence=r["evidence"], done=bool(r["done"]),
                      mail_subject=r["mail_subject"]) for r in rows]
    # Dated tasks first, by date (parsed: strings can carry different UTC offsets); then undated.
    far_future = datetime.max.replace(tzinfo=timezone.utc)
    return sorted(items, key=lambda d: datetime.fromisoformat(d.due_iso) if d.due_iso else far_future)


def set_deadline_done(deadline_id: int, done: bool) -> bool:
    with get_conn() as conn:
        cur = conn.execute("UPDATE deadlines SET done = ? WHERE id = ?", (int(done), deadline_id))
    return cur.rowcount > 0


# ---- drafts + feedback ----

def save_draft(mail_id: str | None, instruction: str, email: GeneratedEmail) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO drafts (mail_id, instruction, subject, body, sources_json, issues_json, "
            "model, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (mail_id, instruction, email.subject, email.body,
             json.dumps([s.id for s in email.sources]), json.dumps(email.issues),
             email.model, now_iso()),
        )
    return cur.lastrowid


def save_feedback(draft_id: int, fb: Feedback) -> bool:
    with get_conn() as conn:
        if not conn.execute("SELECT 1 FROM drafts WHERE id = ?", (draft_id,)).fetchone():
            return False
        conn.execute("INSERT INTO feedback (draft_id, rating, comment, created_at) "
                     "VALUES (?, ?, ?, ?)", (draft_id, fb.rating, fb.comment, now_iso()))
    return True
