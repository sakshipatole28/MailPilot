"""Background processing of new mail: index it for search, then triage it.

One worker thread drains a queue of mail ids. A single worker is deliberate: it keeps LLM calls
sequential, which is what free-tier rate limits want, and the client's retry/backoff handles the
rest. Work happens on the server, so it continues after the popup is closed.
"""
import logging
import queue
import threading

from app import db
from app.llm.client import LLMError
from app.llm.triage import triage_mail
from app.models import LLMOptions, Mail
from app.rag.chunker import Chunk

log = logging.getLogger("mailpilot.jobs")


def mail_chunk(mail: Mail) -> Chunk:
    text = f"{mail.subject}\n{mail.summary}\n{mail.body[:1500]}".strip()
    return Chunk(id=mail.id, text=text, meta={
        "source": mail.id, "title": mail.subject[:200], "doc_type": "mail",
        "category": mail.category or "any", "contact": "",
    })


def index_mails(mails: list[Mail]) -> None:
    """Add or refresh mails in the search index used by "Ask your inbox"."""
    from app.deps import get_mail_retriever

    get_mail_retriever().store.upsert([mail_chunk(m) for m in mails])


def run_triage(mail_ids: list[str], opts: LLMOptions) -> tuple[list[Mail], list[str]]:
    """Triage the given mails now. Returns (triaged mails, ids that failed)."""
    from app.api.settings import runtime_settings

    current = runtime_settings()
    corrected = db.corrected_mails()
    known = db.replied_senders()
    done, failed = [], []
    for mail in db.get_mails(mail_ids):
        try:
            updated, tasks = triage_mail(mail, opts, current.categories, current.user_name,
                                         corrected, known)
        except LLMError as e:
            db.set_triage_status([mail.id], "failed", str(e))
            failed.append(mail.id)
            log.warning("triage failed for %s: %s", mail.id, e)
            continue
        db.save_triage(updated)
        db.save_deadlines(tasks)
        done.append(db.get_mail(mail.id))
    return done, failed


class Worker:
    def __init__(self):
        self.queue: queue.Queue[str] = queue.Queue()
        self.queued: set[str] = set()
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if self.thread is None:
            self.thread = threading.Thread(target=self._loop, name="mailpilot-worker", daemon=True)
            self.thread.start()

    def enqueue(self, mail_ids: list[str]) -> int:
        with self.lock:
            fresh = [i for i in mail_ids if i not in self.queued]
            self.queued.update(fresh)
        if fresh:
            db.set_triage_status(fresh, "pending")
        for mail_id in fresh:
            self.queue.put(mail_id)
        return len(fresh)

    def pending(self) -> int:
        return self.queue.qsize()

    def _loop(self) -> None:
        from app.api.settings import runtime_settings

        while True:
            mail_id = self.queue.get()
            try:
                if db.get_mail(mail_id) is None:
                    continue
                current = runtime_settings()
                if not current.auto_triage:
                    db.set_triage_status([mail_id], None)
                elif current.local_only and not current.model.startswith("ollama/"):
                    db.set_triage_status([mail_id], "failed", "local-only mode needs an ollama model")
                else:
                    run_triage([mail_id], LLMOptions(model=current.model))
                try:
                    index_mails([db.get_mail(mail_id)])  # after triage, so the summary is searchable
                except Exception as e:  # a search-index problem must not stop triage
                    log.warning("indexing failed for %s: %s", mail_id, e)
            except Exception as e:  # keep the worker alive whatever happens to one mail
                log.exception("worker error on %s: %s", mail_id, e)
                db.set_triage_status([mail_id], "failed", str(e))
            finally:
                with self.lock:
                    self.queued.discard(mail_id)


worker = Worker()
