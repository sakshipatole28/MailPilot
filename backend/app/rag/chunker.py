"""Split context documents into chunks with metadata from a small front-matter header.

A document may start with:
    ---
    type: reply          (resume | reply | note | project ...; default: folder name)
    category: Placement  (which mail category it is relevant to; default: any)
    contact: hr@x.com    (only use when replying to this sender; default: anyone)
    title: ...
    ---
"""
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Chunk:
    id: str
    text: str
    meta: dict = field(default_factory=dict)


def parse_front_matter(raw: str) -> tuple[dict, str]:
    lines = raw.lstrip().splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, raw
    meta = {}
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return meta, "\n".join(lines[i + 1:])
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip().lower()] = value.strip()
    return {}, raw  # no closing ---: treat everything as body


def chunk_text(text: str, max_words: int = 120, overlap: int = 30) -> list[str]:
    """Pack whole paragraphs up to max_words; split overly long paragraphs with a word overlap."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, current, current_len = [], [], 0

    def flush():
        nonlocal current, current_len
        if current:
            chunks.append("\n\n".join(current))
        current, current_len = [], 0

    for para in paragraphs:
        words = para.split()
        if len(words) > max_words:
            flush()
            step = max_words - overlap
            for start in range(0, len(words), step):
                chunks.append(" ".join(words[start:start + max_words]))
                if start + max_words >= len(words):
                    break
            continue
        if current_len + len(words) > max_words:
            flush()
        current.append(para)
        current_len += len(words)
    flush()
    return chunks


def chunk_file(path: Path, root: Path) -> list[Chunk]:
    meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
    rel = path.relative_to(root).as_posix()
    base = {
        "source": rel,
        "title": meta.get("title", path.stem.replace("_", " ")),
        "doc_type": meta.get("type", path.parent.name if path.parent != root else "note"),
        "category": meta.get("category", "any"),
        "contact": meta.get("contact", "").lower(),
    }
    return [Chunk(id=f"{rel}#{i}", text=text, meta=dict(base))
            for i, text in enumerate(chunk_text(body))]
