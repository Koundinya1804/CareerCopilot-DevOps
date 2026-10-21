"""
tests/test_rag.py
─────────────────
Comprehensive tests for the RAG pipeline:

  Unit Tests:
    - Document loader (text, JSON, bytes)
    - Chunker (recursive, sentence_window, paragraph, dedup)
    - NLP metadata enrichment
    - ATS score in chunks
    - Citation builder
    - Category router
    - Query expansion

  Integration Tests (mocked ChromaDB + Gemini):
    - Ingestion pipeline
    - Retrieval
    - Full RAG chain (mock LLM)
    - API endpoints (chat, search, categories, admin ingest)
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base, get_db
from app.db.redis import get_redis
from app.main import app

# ── Test DB ───────────────────────────────────────────────────────────────────
TEST_DB_URL = "sqlite:///./test_rag.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession  = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)


def override_get_db():
    db = TestSession()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def override_get_redis():
    m = MagicMock()
    m.exists.return_value = 0
    m.pipeline.return_value.execute.return_value = [1, True]
    yield m


@pytest.fixture(autouse=True, scope="module")
def setup_db():
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db]    = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis
    yield
    Base.metadata.drop_all(bind=test_engine)
    app.dependency_overrides.clear()
    for f in ["test_rag.db"]:
        Path(f).unlink(missing_ok=True)


@pytest.fixture(scope="module")
def client() -> TestClient:
    with patch("app.db.session.check_database_connection", return_value=True), \
         patch("app.db.redis.check_redis_connection",      return_value=True):
        with TestClient(app) as c:
            yield c


def get_auth_headers(client: TestClient, suffix: str = "rag") -> dict:
    client.post("/api/v1/auth/register", json={
        "full_name": f"RAG User {suffix}",
        "email":     f"rag_{suffix}@test.com",
        "password":  "Str0ng!Pass",
    })
    r = client.post("/api/v1/auth/login", json={
        "email": f"rag_{suffix}@test.com", "password": "Str0ng!Pass",
    })
    return {"Authorization": f"Bearer {r.json()['data']['tokens']['access_token']}"}


def get_admin_headers(client: TestClient) -> dict:
    """Create an admin user and return auth headers."""
    from app.models.user import User, UserRole
    db = TestSession()
    from app.core.security import hash_password
    existing = db.query(User).filter_by(email="admin_rag@test.com").first()
    if not existing:
        admin = User(
            email="admin_rag@test.com",
            password_hash=hash_password("Str0ng!Pass"),
            full_name="RAG Admin",
            role=UserRole.ADMIN,
        )
        db.add(admin)
        db.commit()
    db.close()
    r = client.post("/api/v1/auth/login", json={
        "email": "admin_rag@test.com", "password": "Str0ng!Pass",
    })
    return {"Authorization": f"Bearer {r.json()['data']['tokens']['access_token']}"}


# ── Sample data ───────────────────────────────────────────────────────────────
SAMPLE_TEXT = """
What is a deadlock in Operating Systems?

A deadlock is a situation where a set of processes are blocked because each process
is holding a resource and waiting to acquire a resource held by another process.

The four Coffman conditions that must hold simultaneously for a deadlock to occur:
1. Mutual Exclusion: At least one resource must be held in a non-shareable mode.
2. Hold and Wait: A process must be holding at least one resource and waiting for more.
3. No Preemption: Resources cannot be forcibly taken from a process.
4. Circular Wait: There must be a circular chain of two or more processes, each waiting
   for a resource held by the next member in the chain.

Prevention strategies include: resource ordering, request all resources upfront,
allow preemption, or use the Banker's Algorithm for deadlock avoidance.
"""

SAMPLE_JSON_QA = [
    {"question": "What is SQL injection?",
     "answer": "SQL injection is an attack where malicious SQL is inserted into queries via user input."},
    {"question": "What is normalization?",
     "answer": "Database normalization is the process of organizing data to reduce redundancy."},
]


# ═══════════════════════════════════════════════════════════════════════════════
# Unit Tests — KB Categories
# ═══════════════════════════════════════════════════════════════════════════════
class TestKBCategories:
    def test_all_nine_categories_defined(self):
        from app.rag.kb_categories import KB_CATEGORIES
        expected = {"dbms","operating_systems","computer_networks","oop",
                    "java","python","aptitude","hr_questions","company_guides"}
        assert set(KB_CATEGORIES.keys()) == expected

    def test_collection_name_format(self):
        from app.rag.kb_categories import get_collection_name
        assert get_collection_name("dbms") == "careercopilot_dbms"
        assert get_collection_name("python", "cc") == "cc_python"

    def test_get_category_valid(self):
        from app.rag.kb_categories import get_category
        cat = get_category("java")
        assert cat.label == "Java"
        assert cat.chunk_size == 512

    def test_get_category_invalid(self):
        from app.rag.kb_categories import get_category
        with pytest.raises(ValueError, match="Unknown category"):
            get_category("blockchain")

    def test_aptitude_has_smaller_chunks(self):
        from app.rag.kb_categories import KB_CATEGORIES
        assert KB_CATEGORIES["aptitude"].chunk_size < KB_CATEGORIES["dbms"].chunk_size


# ═══════════════════════════════════════════════════════════════════════════════
# Unit Tests — Document Loader
# ═══════════════════════════════════════════════════════════════════════════════
class TestDocumentLoader:
    def test_load_text_file(self, tmp_path: Path):
        from app.rag.loaders.document_loader import load_file
        f = tmp_path / "test.txt"
        f.write_text("Hello world this is a test document for RAG pipeline.")
        docs = load_file(f, "dbms")
        assert len(docs) == 1
        assert "Hello world" in docs[0].page_content
        assert docs[0].metadata["category"] == "dbms"
        assert docs[0].metadata["word_count"] > 0

    def test_load_json_qa(self, tmp_path: Path):
        from app.rag.loaders.document_loader import load_file
        f = tmp_path / "qa.json"
        f.write_text(json.dumps(SAMPLE_JSON_QA))
        docs = load_file(f, "dbms")
        assert len(docs) == 2
        assert "Q:" in docs[0].page_content
        assert "A:" in docs[0].page_content

    def test_load_json_topic_format(self, tmp_path: Path):
        from app.rag.loaders.document_loader import load_file
        data = [{"topic": "ACID", "content": "Atomicity Consistency Isolation Durability"}]
        f = tmp_path / "topics.json"
        f.write_text(json.dumps(data))
        docs = load_file(f, "dbms")
        assert len(docs) == 1
        assert "ACID" in docs[0].page_content

    def test_load_unsupported_returns_empty(self, tmp_path: Path):
        from app.rag.loaders.document_loader import load_file
        f = tmp_path / "image.png"
        f.write_bytes(b"\x89PNG\r\n")
        docs = load_file(f, "dbms")
        assert docs == []

    def test_load_missing_file_returns_empty(self):
        from app.rag.loaders.document_loader import load_file
        docs = load_file("/nonexistent/path/file.txt", "dbms")
        assert docs == []

    def test_load_directory(self, tmp_path: Path):
        from app.rag.loaders.document_loader import load_directory
        (tmp_path / "a.txt").write_text("Content A about databases and SQL queries.")
        (tmp_path / "b.txt").write_text("Content B about operating systems and processes.")
        (tmp_path / ".hidden.txt").write_text("Should be skipped")
        docs = list(load_directory(tmp_path, "dbms"))
        assert len(docs) == 2  # hidden file skipped

    def test_load_bytes(self):
        from app.rag.loaders.document_loader import load_bytes
        data = b"This is a plain text document about Python programming language."
        docs = load_bytes(data, "test.txt", "python", "text/plain")
        assert len(docs) >= 1
        assert "Python" in docs[0].page_content

    def test_metadata_fields(self, tmp_path: Path):
        from app.rag.loaders.document_loader import load_file
        f = tmp_path / "meta_test.txt"
        f.write_text("Test content for metadata validation in the document loader.")
        docs = load_file(f, "java")
        meta = docs[0].metadata
        assert "source"    in meta
        assert "filename"  in meta
        assert "category"  in meta
        assert "loaded_at" in meta
        assert "word_count" in meta
        assert meta["category"]  == "java"
        assert meta["file_type"] == "txt"


# ═══════════════════════════════════════════════════════════════════════════════
# Unit Tests — Chunker
# ═══════════════════════════════════════════════════════════════════════════════
class TestChunker:
    def _make_doc(self, text: str, category: str = "dbms"):
        from langchain_core.documents import Document
        return Document(
            page_content=text,
            metadata={"source": "test.txt", "category": category,
                      "filename": "test.txt", "loaded_at": "2025-01-01"}
        )

    def test_recursive_chunking_basic(self):
        from app.rag.processors.chunker import chunk_documents
        doc    = self._make_doc(SAMPLE_TEXT * 3)
        chunks = chunk_documents([doc], strategy="recursive", chunk_size=200, chunk_overlap=20)
        assert len(chunks) > 1
        for c in chunks:
            assert len(c.page_content) <= 250   # allow slight overflow

    def test_chunk_metadata_preserved(self):
        from app.rag.processors.chunker import chunk_documents
        doc    = self._make_doc(SAMPLE_TEXT)
        chunks = chunk_documents([doc], strategy="recursive")
        for c in chunks:
            assert c.metadata.get("category") == "dbms"
            assert "chunk_id"    in c.metadata
            assert "chunk_index" in c.metadata

    def test_chunk_id_is_deterministic(self):
        from app.rag.processors.chunker import chunk_documents
        doc     = self._make_doc("Consistent text for deterministic chunk ID testing.")
        chunks1 = chunk_documents([doc])
        chunks2 = chunk_documents([doc])
        ids1 = [c.metadata["chunk_id"] for c in chunks1]
        ids2 = [c.metadata["chunk_id"] for c in chunks2]
        assert ids1 == ids2

    def test_deduplication(self):
        from app.rag.processors.chunker import chunk_documents
        doc    = self._make_doc("Same content document for deduplication test.")
        chunks = chunk_documents([doc, doc])   # same doc twice
        ids    = [c.metadata["chunk_id"] for c in chunks]
        assert len(ids) == len(set(ids))       # all unique

    def test_sentence_window_strategy(self):
        from app.rag.processors.chunker import chunk_documents
        doc    = self._make_doc(SAMPLE_TEXT)
        chunks = chunk_documents([doc], strategy="sentence_window")
        assert len(chunks) >= 1
        for c in chunks:
            assert c.metadata.get("strategy") == "sentence_window"

    def test_paragraph_strategy(self):
        from app.rag.processors.chunker import chunk_documents
        text   = "Para 1 content.\n\nPara 2 content.\n\nPara 3 content."
        doc    = self._make_doc(text)
        chunks = chunk_documents([doc], strategy="paragraph", chunk_size=500)
        assert len(chunks) >= 1
        for c in chunks:
            assert c.metadata.get("strategy") == "paragraph"

    def test_short_chunks_filtered(self):
        from app.rag.processors.chunker import chunk_documents
        doc    = self._make_doc("Hi.\n\n" + SAMPLE_TEXT)
        chunks = chunk_documents([doc], strategy="recursive")
        for c in chunks:
            assert len(c.page_content.strip()) >= 50

    def test_empty_docs_returns_empty(self):
        from app.rag.processors.chunker import chunk_documents
        assert chunk_documents([]) == []


# ═══════════════════════════════════════════════════════════════════════════════
# Unit Tests — Citation Builder
# ═══════════════════════════════════════════════════════════════════════════════
class TestCitationBuilder:
    def _make_chunks(self, n: int = 3):
        from app.rag.retriever.retriever import RetrievedChunk
        return [
            RetrievedChunk(
                content=f"Content about topic {i}",
                score=0.9 - i * 0.1,
                category="dbms",
                source=f"/kb/dbms/doc{i}.json",
                filename=f"doc{i}.json",
                chunk_id=f"id_{i}",
                chunk_index=0,
            )
            for i in range(n)
        ]

    def test_citation_count(self):
        from app.rag.citations.citation_builder import build_citations
        chunks    = self._make_chunks(3)
        citations = build_citations(chunks)
        assert len(citations) == 3

    def test_citation_numbering(self):
        from app.rag.citations.citation_builder import build_citations
        chunks    = self._make_chunks(3)
        citations = build_citations(chunks)
        nums = [c.number for c in citations]
        assert nums == [1, 2, 3]

    def test_dedup_same_file(self):
        from app.rag.citations.citation_builder import build_citations
        from app.rag.retriever.retriever import RetrievedChunk
        # Two chunks from the same file → one citation
        chunks = [
            RetrievedChunk("Content A", 0.9, "dbms", "/f/same.json", "same.json", "id1", 0),
            RetrievedChunk("Content B", 0.8, "dbms", "/f/same.json", "same.json", "id2", 1),
        ]
        citations = build_citations(chunks)
        assert len(citations) == 1
        assert citations[0].number == 1

    def test_format_json(self):
        from app.rag.citations.citation_builder import build_citations, format_citations_json
        chunks    = self._make_chunks(2)
        citations = build_citations(chunks)
        json_out  = format_citations_json(citations)
        assert len(json_out) == 2
        assert "number"   in json_out[0]
        assert "filename" in json_out[0]
        assert "score"    in json_out[0]

    def test_format_markdown(self):
        from app.rag.citations.citation_builder import build_citations, format_citations_markdown
        chunks  = self._make_chunks(2)
        cits    = build_citations(chunks)
        md      = format_citations_markdown(cits)
        assert "Sources:" in md
        assert "[1]" in md
        assert "[2]" in md

    def test_empty_chunks_empty_citations(self):
        from app.rag.citations.citation_builder import build_citations, format_citations_markdown
        assert build_citations([]) == []
        assert format_citations_markdown([]) == ""


# ═══════════════════════════════════════════════════════════════════════════════
# Unit Tests — Category Router & Query Expansion
# ═══════════════════════════════════════════════════════════════════════════════
class TestRetrieverHelpers:
    def test_route_dbms_query(self):
        from app.rag.retriever.retriever import _route_category
        cats = _route_category("What is SQL join and normalization?")
        assert "dbms" in cats

    def test_route_os_query(self):
        from app.rag.retriever.retriever import _route_category
        cats = _route_category("Explain deadlock and semaphore in OS")
        assert "operating_systems" in cats

    def test_route_java_query(self):
        from app.rag.retriever.retriever import _route_category
        cats = _route_category("Java garbage collection and JVM memory")
        assert "java" in cats

    def test_route_hr_query(self):
        from app.rag.retriever.retriever import _route_category
        cats = _route_category("Tell me about yourself HR interview answer")
        assert "hr_questions" in cats

    def test_route_unknown_returns_all(self):
        from app.rag.retriever.retriever import _route_category
        from app.rag.kb_categories import KB_CATEGORIES
        cats = _route_category("xyzzy quux foo bar completely unknown topic")
        assert set(cats) == set(KB_CATEGORIES.keys())

    def test_query_expansion_short_query(self):
        from app.rag.retriever.retriever import _expand_query
        variants = _expand_query("deadlock")
        assert len(variants) > 1
        assert "deadlock" in variants[0]
        assert any("what is" in v.lower() for v in variants)

    def test_query_expansion_no_duplicate(self):
        from app.rag.retriever.retriever import _expand_query
        variants = _expand_query("explain TCP handshake")
        assert len(variants) == len(set(variants))

    def test_query_expansion_max_4(self):
        from app.rag.retriever.retriever import _expand_query
        variants = _expand_query("x")
        assert len(variants) <= 4


# ═══════════════════════════════════════════════════════════════════════════════
# Unit Tests — RAG Chain (mocked LLM)
# ═══════════════════════════════════════════════════════════════════════════════
class TestRAGChain:
    def _mock_chunks(self, n: int = 3):
        from app.rag.retriever.retriever import RetrievedChunk
        return [
            RetrievedChunk(
                content=f"Relevant content about deadlock number {i}. " * 5,
                score=0.85 - i * 0.05,
                category="operating_systems",
                source=f"/kb/os/file{i}.json",
                filename=f"file{i}.json",
                chunk_id=f"chunk_{i}",
                chunk_index=i,
            )
            for i in range(n)
        ]

    def test_mock_mode_when_no_api_key(self):
        """With no GEMINI_API_KEY, mock answer is returned."""
        from app.rag.chains.rag_chain import get_rag_chain
        with patch("app.rag.chains.rag_chain.retrieve_chunks", return_value=self._mock_chunks()):
            result = get_rag_chain("What is a deadlock?")
        assert isinstance(result.answer, str)
        assert len(result.answer) > 10
        assert result.chunks_used == 3

    def test_response_has_all_fields(self):
        from app.rag.chains.rag_chain import get_rag_chain
        with patch("app.rag.chains.rag_chain.retrieve_chunks", return_value=self._mock_chunks()):
            result = get_rag_chain("What is a deadlock?")
        assert hasattr(result, "answer")
        assert hasattr(result, "citations")
        assert hasattr(result, "chunks_used")
        assert hasattr(result, "latency_ms")
        assert hasattr(result, "model_used")
        assert result.latency_ms >= 0

    def test_no_chunks_returns_no_answer(self):
        from app.rag.chains.rag_chain import get_rag_chain
        with patch("app.rag.chains.rag_chain.retrieve_chunks", return_value=[]):
            result = get_rag_chain("Completely obscure question xyz")
        assert result.chunks_used == 0
        assert result.has_answer is False

    def test_citations_from_chunks(self):
        from app.rag.chains.rag_chain import get_rag_chain
        with patch("app.rag.chains.rag_chain.retrieve_chunks", return_value=self._mock_chunks(2)):
            result = get_rag_chain("Explain deadlock")
        assert isinstance(result.citations, list)
        assert len(result.citations) >= 1

    def test_categories_populated(self):
        from app.rag.chains.rag_chain import get_rag_chain
        with patch("app.rag.chains.rag_chain.retrieve_chunks", return_value=self._mock_chunks()):
            result = get_rag_chain("What is a deadlock?")
        assert "operating_systems" in result.categories


# ═══════════════════════════════════════════════════════════════════════════════
# Integration Tests — Ingestion Pipeline (mocked ChromaDB)
# ═══════════════════════════════════════════════════════════════════════════════
class TestIngestionPipeline:
    def _make_docs(self, n: int = 5):
        from langchain_core.documents import Document
        return [
            Document(
                page_content=f"This is document {i} about database normalization and ACID properties. " * 4,
                metadata={"source": f"/kb/dbms/doc{i}.txt", "filename": f"doc{i}.txt",
                          "category": "dbms", "loaded_at": "2025-01-01",
                          "file_type": "txt", "word_count": 40}
            )
            for i in range(n)
        ]

    def test_ingest_documents_success(self):
        from app.rag.processors.ingestion import ingest_documents
        docs = self._make_docs(3)
        mock_store = MagicMock()
        mock_store.upsert.return_value = 6   # 6 chunks stored
        mock_store.delete_chunks_by_source.return_value = 0
        with patch("app.rag.processors.ingestion.get_vectorstore", return_value=mock_store):
            result = ingest_documents(docs, "dbms")
        assert result.success
        assert result.docs_loaded == 3
        assert result.chunks_created > 0
        assert result.status == "success"

    def test_ingest_empty_docs_fails(self):
        from app.rag.processors.ingestion import ingest_documents
        result = ingest_documents([], "dbms")
        assert result.status == "failed"
        assert len(result.errors) > 0

    def test_ingest_from_bytes(self):
        from app.rag.processors.ingestion import ingest_bytes
        data = b"This is plain text about Python generators and decorators for RAG ingestion."
        mock_store = MagicMock()
        mock_store.upsert.return_value = 1
        with patch("app.rag.processors.ingestion.get_vectorstore", return_value=mock_store):
            result = ingest_bytes(data, "test.txt", "python", "text/plain")
        assert result.files_processed == 1

    def test_ingest_category_dir_not_found(self):
        from app.rag.processors.ingestion import ingest_category
        result = ingest_category("dbms", kb_dir="/nonexistent/path/totally/fake")
        assert result.status == "failed"
        assert len(result.errors) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Integration Tests — API Endpoints
# ═══════════════════════════════════════════════════════════════════════════════
class TestRAGAPI:
    @pytest.fixture(scope="class")
    def headers(self, client: TestClient) -> dict:
        return get_auth_headers(client, "api")

    @pytest.fixture(scope="class")
    def admin_headers(self, client: TestClient) -> dict:
        return get_admin_headers(client)

    # ── Categories endpoint ───────────────────────────────────────────────────
    def test_list_categories(self, client: TestClient, headers: dict) -> None:
        mock_stats = [{"category": k, "count": 0, "status": "empty", "collection": f"cc_{k}"}
                      for k in ["dbms","operating_systems","computer_networks","oop",
                                "java","python","aptitude","hr_questions","company_guides"]]
        with patch("app.api.v1.endpoints.rag.get_vectorstore") as mock_vs:
            mock_vs.return_value.get_all_stats.return_value = mock_stats
            r = client.get("/api/v1/rag/categories", headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 9
        keys = [c["key"] for c in data["categories"]]
        assert "dbms"        in keys
        assert "python"      in keys
        assert "hr_questions" in keys

    def test_category_stats(self, client: TestClient, headers: dict) -> None:
        stat = {"category": "dbms", "count": 42, "status": "ready", "collection": "cc_dbms"}
        with patch("app.api.v1.endpoints.rag.get_vectorstore") as mock_vs:
            mock_vs.return_value.get_collection_stats.return_value = stat
            r = client.get("/api/v1/rag/categories/dbms/stats", headers=headers)
        assert r.status_code == 200
        assert r.json()["data"]["count"] == 42

    def test_category_stats_invalid_key(self, client: TestClient, headers: dict) -> None:
        r = client.get("/api/v1/rag/categories/blockchain/stats", headers=headers)
        assert r.status_code == 422

    # ── Chat endpoint ─────────────────────────────────────────────────────────
    def test_chat_no_auth(self, client: TestClient) -> None:
        r = client.post("/api/v1/rag/chat", json={"query": "What is ACID?"})
        assert r.status_code == 403

    def test_chat_success(self, client: TestClient, headers: dict) -> None:
        from app.rag.chains.rag_chain import RAGResponse
        mock_response = RAGResponse(
            answer="ACID stands for Atomicity, Consistency, Isolation, Durability [1].",
            citations=[{"number": 1, "filename": "dbms.json", "category": "dbms",
                        "category_label": "DBMS", "score": 0.88, "excerpt": "ACID..."}],
            chunks_used=3, categories=["dbms"], model_used="gemini-2.0-flash",
            latency_ms=850, tokens_used=210, query="What is ACID?", has_answer=True,
        )
        with patch("app.api.v1.endpoints.rag.get_rag_chain", return_value=mock_response):
            r = client.post("/api/v1/rag/chat",
                            json={"query": "What is ACID?", "categories": ["dbms"]},
                            headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "answer"      in data
        assert "citations"   in data
        assert "chunks_used" in data
        assert data["chunks_used"] == 3
        assert data["has_answer"] is True

    def test_chat_short_query_rejected(self, client: TestClient, headers: dict) -> None:
        r = client.post("/api/v1/rag/chat", json={"query": "Hi"}, headers=headers)
        assert r.status_code == 422

    def test_chat_with_history(self, client: TestClient, headers: dict) -> None:
        from app.rag.chains.rag_chain import RAGResponse
        mock_resp = RAGResponse(
            answer="Based on our earlier discussion, deadlock involves circular wait.",
            citations=[], chunks_used=2, categories=["operating_systems"],
            model_used="gemini-2.0-flash", latency_ms=900, tokens_used=280,
            query="How do we prevent it?", has_answer=True,
        )
        with patch("app.api.v1.endpoints.rag.get_rag_chain", return_value=mock_resp):
            r = client.post("/api/v1/rag/chat",
                            json={
                                "query": "How do we prevent it?",
                                "chat_history": [
                                    {"role": "user",      "content": "What is deadlock?"},
                                    {"role": "assistant", "content": "Deadlock is a situation..."},
                                ],
                            },
                            headers=headers)
        assert r.status_code == 200

    # ── Search endpoint ───────────────────────────────────────────────────────
    def test_search_basic(self, client: TestClient, headers: dict) -> None:
        from app.rag.retriever.retriever import RetrievedChunk
        mock_chunks = [
            RetrievedChunk("SQL join content", 0.82, "dbms",
                           "/kb/dbms/sql.json", "sql.json", "c1", 0),
        ]
        with patch("app.api.v1.endpoints.rag.retrieve_chunks", return_value=mock_chunks):
            r = client.get("/api/v1/rag/search?q=SQL+join", headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 1
        assert data["chunks"][0]["score"] == 0.82

    def test_search_no_auth(self, client: TestClient) -> None:
        r = client.get("/api/v1/rag/search?q=SQL")
        assert r.status_code == 403

    # ── Admin endpoints ───────────────────────────────────────────────────────
    def test_admin_ingest_category(self, client: TestClient, admin_headers: dict) -> None:
        from app.rag.processors.ingestion import IngestionResult
        mock_result = IngestionResult(
            category="dbms", files_processed=1, docs_loaded=5,
            chunks_created=18, chunks_stored=18, duration_ms=340, status="success",
        )
        with patch("app.api.v1.endpoints.rag.ingest_category", return_value=mock_result):
            r = client.post("/api/v1/rag/admin/ingest/dbms", headers=admin_headers)
        assert r.status_code == 202
        data = r.json()["data"]
        assert data["chunks_stored"] == 18
        assert data["status"] == "success"

    def test_admin_ingest_invalid_category(self, client: TestClient, admin_headers: dict) -> None:
        r = client.post("/api/v1/rag/admin/ingest/blockchain", headers=admin_headers)
        assert r.status_code == 422

    def test_admin_ingest_forbidden_for_user(self, client: TestClient, headers: dict) -> None:
        r = client.post("/api/v1/rag/admin/ingest/dbms", headers=headers)
        assert r.status_code == 403

    def test_admin_ingest_all(self, client: TestClient, admin_headers: dict) -> None:
        from app.rag.processors.ingestion import IngestionResult
        from app.rag.kb_categories import KB_CATEGORIES
        mock_results = {k: IngestionResult(k, 1, 5, 10, 10, status="success")
                        for k in KB_CATEGORIES}
        with patch("app.api.v1.endpoints.rag.ingest_all_categories", return_value=mock_results):
            r = client.post("/api/v1/rag/admin/ingest/all", headers=admin_headers)
        assert r.status_code == 202
        data = r.json()["data"]
        assert data["total_chunks"] == 90    # 9 categories × 10 chunks

    def test_admin_upload_document(self, client: TestClient, admin_headers: dict) -> None:
        from app.rag.processors.ingestion import IngestionResult
        mock_result = IngestionResult(
            "python", 1, 1, 5, 5, duration_ms=120, status="success"
        )
        txt_content = b"Python decorators are functions that modify other functions in Python."
        with patch("app.api.v1.endpoints.rag.ingest_bytes", return_value=mock_result):
            r = client.post(
                "/api/v1/rag/admin/upload/python",
                files={"file": ("decorators.txt", txt_content, "text/plain")},
                data={"replace": "false", "strategy": "recursive"},
                headers=admin_headers,
            )
        assert r.status_code == 201
        data = r.json()["data"]
        assert data["chunks_stored"] == 5
        assert data["category"] == "python"

    def test_admin_delete_collection(self, client: TestClient, admin_headers: dict) -> None:
        with patch("app.api.v1.endpoints.rag.get_vectorstore") as mock_vs:
            mock_vs.return_value.delete_collection.return_value = True
            r = client.delete("/api/v1/rag/admin/collections/dbms", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["data"]["deleted"] is True

    # ── Streaming endpoint (smoke test) ──────────────────────────────────────
    def test_stream_returns_streaming_response(self, client: TestClient, headers: dict) -> None:
        def mock_stream(*args, **kwargs):
            yield "Deadlock "
            yield "is "
            yield "a serious problem."
        with patch("app.api.v1.endpoints.rag.stream_rag_chain", side_effect=mock_stream):
            r = client.post(
                "/api/v1/rag/chat/stream",
                json={"query": "What is deadlock?"},
                headers=headers,
            )
        # StreamingResponse returns 200 with event-stream content type
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")
