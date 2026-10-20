from app.config import ROOT
from app.rag.chunker import chunk_file, chunk_text, parse_front_matter
from app.rag.ingest import ingest_dir
from app.rag.retriever import Retriever, build_where, rrf
from app.rag.store import VectorStore

CONTEXT = ROOT / "data" / "context"


def test_front_matter():
    meta, body = parse_front_matter("---\ntype: reply\ncategory: Academic\n---\nHello")
    assert meta == {"type": "reply", "category": "Academic"} and body.strip() == "Hello"
    assert parse_front_matter("No header") == ({}, "No header")


def test_chunk_text_packs_paragraphs_and_splits_long_ones():
    short = "one two three\n\nfour five"
    assert chunk_text(short, max_words=10) == ["one two three\n\nfour five"]
    long_para = " ".join(str(i) for i in range(25))
    chunks = chunk_text(long_para, max_words=10, overlap=2)
    assert all(len(c.split()) <= 10 for c in chunks)
    assert chunks[1].split()[0] == "8"  # 2-word overlap with the previous window


def test_chunk_file_metadata():
    chunks = chunk_file(CONTEXT / "notes" / "fabrikam_thread.md", CONTEXT)
    assert chunks[0].meta["contact"] == "rahul.mehta@fabrikam.io"
    assert chunks[0].meta["category"] == "HR/Recruiter"
    assert chunks[0].id == "notes/fabrikam_thread.md#0"


def test_rrf_rewards_agreement():
    fused = dict(rrf([["a", "b", "c"], ["b", "a", "d"]]))
    assert fused["a"] == fused["b"] > fused["c"] == fused["d"]


def test_build_where():
    assert build_where(None, None, None) is None
    assert build_where("Academic", None, None) == {"category": {"$in": ["Academic", "any"]}}
    assert "$and" in build_where("Academic", "x@y.com", "reply")


def _retriever(tmp_path, fake_embedder):
    store = VectorStore(tmp_path / "chroma", fake_embedder)
    stats = ingest_dir(CONTEXT, store)
    assert stats["files"] >= 10 and stats["chunks"] == store.count()
    return Retriever(store)


def test_hybrid_search_finds_relevant_doc(tmp_path, fake_embedder):
    retriever = _retriever(tmp_path, fake_embedder)
    for mode in ("hybrid", "vector", "bm25"):
        hits = retriever.search("degree certificates and government ID", k=3, mode=mode)
        assert "notes/documents.md" in [h.source for h in hits], mode


def test_contact_filter_hides_other_peoples_threads(tmp_path, fake_embedder):
    retriever = _retriever(tmp_path, fake_embedder)
    query = "Fabrikam stipend internship Pune Rahul"
    for_rahul = retriever.search(query, k=5, contact="rahul.mehta@fabrikam.io")
    for_other = retriever.search(query, k=5, contact="someone@else.com")
    assert "notes/fabrikam_thread.md" in [h.source for h in for_rahul]
    assert "notes/fabrikam_thread.md" not in [h.source for h in for_other]


def test_doc_type_filter_returns_style_examples(tmp_path, fake_embedder):
    retriever = _retriever(tmp_path, fake_embedder)
    hits = retriever.search("interview slot", k=2, doc_type="reply")
    assert hits and all(h.source.startswith("replies/") for h in hits)
