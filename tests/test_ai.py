"""
Hermetic tests for the src/ai/ modules (ADR-017).
--------------------------------------------------
All tests are fully mocked — zero live ollama calls, zero real DB writes.
Coverage: cosine math, llm_client (chat/embed/is_available), intent parsing,
agent tool loop + deterministic fallback, RAG indexer search, config v3
migration, and the chat.py AI-first wiring contract.
"""
import json

import pytest

from src.ai import llm_client, embed
from src.ai.assistant_llm import parse_intent, generate_rag_answer
from src.ai.agent import Agent, agent
from src.ai.rag_indexer import RagIndexer
from src.services.config_service import (
    DEFAULT_CONFIG,
    MIGRATIONS,
    SCHEMA_VERSION,
)

# Lock AI config to a hermetic shape for every test
AI_CFG = {
    "enabled": True,
    "model": "qwen3:0.6b",
    "embed_model": "nomic-embed-text",
    "timeout_s": 30,
    "index_interval_s": 300,
}


@pytest.fixture(autouse=True)
def _hermetic_ai_config():
    """Every test gets an enabled AI section (no live ollama involved)."""
    import src.services.config_service as cs

    original = cs.config_service.config.get("ai")
    cs.config_service.config["ai"] = dict(AI_CFG)
    yield
    if original is None:
        cs.config_service.config.pop("ai", None)
    else:
        cs.config_service.config["ai"] = original


# ---------------------------------------------------------------------------
# cosine similarity (pure math — no mocks needed)
# ---------------------------------------------------------------------------

class TestCosine:
    def test_identical_vectors(self):
        assert embed.cosine([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert embed.cosine([1.0, 0.0, 0.0], [0.0, 1.0, 0.0]) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        assert embed.cosine([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_angle_45(self):
        assert embed.cosine([1.0, 0.0], [1.0, 1.0]) == pytest.approx(1 / 2 ** 0.5)

    def test_dimension_mismatch_returns_zero(self):
        assert embed.cosine([1.0, 0.0], [1.0, 0.0, 0.0]) == 0.0

    def test_zero_vector_returns_zero(self):
        assert embed.cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


# ---------------------------------------------------------------------------
# llm_client — HTTP contract via mocked urllib
# ---------------------------------------------------------------------------

class TestLlmClient:
    def test_chat_passes_think_false_and_json_format(self, mocker):
        """q3:0.6b quirk: 'think': false must reach the payload (ADR-017)."""
        fake_response = json.dumps({"response": '{"tool": "search"}'}).encode()

        def _fake_urlopen(req, timeout=None):
            body = json.loads(req.data)
            assert body["think"] is False
            assert body["stream"] is False
            assert body["format"] == "json"
            assert body["model"] == "qwen3:0.6b"
            assert body["options"]["num_predict"] == 256
            return mocker.MagicMock(
                __enter__=lambda s: mocker.MagicMock(read=lambda: fake_response),
                __exit__=lambda *a: None,
            )

        mocker.patch("urllib.request.urlopen", side_effect=_fake_urlopen)
        out = llm_client.chat("qwen3:0.6b", "hello")
        assert out == '{"tool": "search"}'

    def test_embed_returns_first_vector(self, mocker):
        payload = {"embeddings": [[0.1, 0.2, 0.3], [1.1, 2.2]]}
        fake = json.dumps(payload).encode()

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return fake

        mocker.patch("urllib.request.urlopen", return_value=FakeResp())
        vec = llm_client.embed("nomic-embed-text", "hello")
        assert vec == [0.1, 0.2, 0.3]

    def test_embed_empty_result_raises(self, mocker):
        mocker.patch(
            "urllib.request.urlopen",
            return_value=mocker.MagicMock(
                __enter__=lambda s: mocker.MagicMock(read=lambda: b'{"embeddings": []}'),
                __exit__=lambda *a: None,
            ),
        )
        with pytest.raises(ValueError):
            llm_client.embed("nomic-embed-text", "x")

    def test_unreachable_host_raises_connection_error(self, mocker):
        import urllib.error

        mocker.patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("refused"),
        )
        with pytest.raises(ConnectionError):
            llm_client.chat("qwen3:0.6b", "hi")

    def test_is_available_returns_false_on_failure(self, mocker):
        # Reset the 60s ping cache so the real function runs against a dead host
        llm_client._last_ping = 0.0
        llm_client._last_ping_result = False
        mocker.patch(
            "urllib.request.urlopen",
            side_effect=Exception("boom"),
        )
        assert llm_client.is_available() is False

    def test_is_available_uses_get_method(self, mocker):
        """Regression: /api/tags only accepts GET (POST → 405), which kept
        is_available() permanently False and silently killed the LLM path."""
        seen = {}

        def _fake_urlopen(req, timeout=None):
            seen["method"] = req.get_method()
            seen["data"] = req.data
            return mocker.MagicMock(
                __enter__=lambda s: mocker.MagicMock(read=lambda: b"{}"),
                __exit__=lambda *a: None,
            )

        llm_client._last_ping = 0.0
        llm_client._last_ping_result = False
        mocker.patch("urllib.request.urlopen", side_effect=_fake_urlopen)
        assert llm_client.is_available() is True
        assert seen["method"] == "GET"
        assert seen["data"] is None

    def test_is_available_caches_result(self, mocker):
        llm_client._last_ping = 0.0
        llm_client._last_ping_result = False
        mocker.patch(
            "urllib.request.urlopen",
            return_value=mocker.MagicMock(
                __enter__=lambda s: mocker.MagicMock(read=lambda: b"{}"),
                __exit__=lambda *a: None,
            ),
        )
        assert llm_client.is_available() is True
        # Second call within TTL must not hit the network
        mocker.patch(
            "urllib.request.urlopen",
            side_effect=AssertionError("cache should have prevented IO"),
        )
        assert llm_client.is_available() is True


# ---------------------------------------------------------------------------
# embedding helpers — prefix discipline (nomic-embed-text contract)
# ---------------------------------------------------------------------------

class TestEmbedPrefixed:
    def test_query_prefix(self, mocker):
        mocker.patch("src.ai.llm_client.embed", return_value=[1.0])
        embed.embed_query("tax docs")
        llm_client.embed.assert_called_once_with(
            "nomic-embed-text", "search_query: tax docs"
        )

    def test_document_prefix(self, mocker):
        mocker.patch("src.ai.llm_client.embed", return_value=[1.0])
        embed.embed_document("report.pdf")
        llm_client.embed.assert_called_once_with(
            "nomic-embed-text", "search_document: report.pdf"
        )


# ---------------------------------------------------------------------------
# intent parsing — one LLM round trip → structured tool JSON
# ---------------------------------------------------------------------------

class TestParseIntent:
    def test_valid_tool_json(self, mocker):
        mocker.patch(
            "src.ai.llm_client.chat",
            return_value='{"tool": "search", "query": "pdfs", "params": {}}',
        )
        parsed = parse_intent("find my pdfs")
        assert parsed == {"tool": "search", "query": "pdfs", "params": {}}

    def test_missing_fields_fill_defaults(self, mocker):
        mocker.patch("src.ai.llm_client.chat", return_value='{"tool": "status"}')
        parsed = parse_intent("status")
        assert parsed["tool"] == "status"
        assert parsed["query"] == "status"
        assert parsed["params"] == {}

    def test_bad_json_returns_unknown(self, mocker):
        mocker.patch("src.ai.llm_client.chat", return_value="not json {")
        parsed = parse_intent("anything")
        assert parsed["tool"] == "unknown"
        assert parsed["query"] == "anything"

    def test_llm_exception_returns_unknown(self, mocker):
        mocker.patch(
            "src.ai.llm_client.chat", side_effect=ConnectionError("down")
        )
        parsed = parse_intent("anything")
        assert parsed["tool"] == "unknown"

    def test_generate_rag_answer_formats_citations(self, mocker):
        mocker.patch(
            "src.ai.llm_client.chat",
            return_value="Here is tax-2025.pdf.",
        )
        ctx = [
            {"filename": "tax-2025.pdf", "category": "PDFs", "snippet": "tax-2025.pdf"},
            {"filename": "receipt.png", "category": "Images", "snippet": "receipt.png"},
        ]
        out = generate_rag_answer("tax?", ctx)
        assert "tax-2025.pdf" in out

    def test_generate_rag_answer_empty_context_returns_empty(self, mocker):
        assert generate_rag_answer("hi", []) == ""


# ---------------------------------------------------------------------------
# agent — tool loop + deterministic fallback ("LLM proposes, code disposes")
# Note: agent.py imports parse_intent/rag_indexer by reference, so mocks target
# the names as bound inside src.ai.agent, not the origin modules.
# ---------------------------------------------------------------------------

@pytest.fixture
def _llm_online(mocker):
    """Agent.process() gates on is_available(); force it True for LLM tests."""
    mocker.patch("src.ai.llm_client.is_available", return_value=True)
    yield


class TestAgent:
    def test_search_tool_returns_response(self, mocker, _llm_online):
        mocker.patch(
            "src.ai.agent.parse_intent",
            return_value={"tool": "search", "query": "pdfs", "params": {}},
        )
        mocker.patch(
            "src.ai.agent.rag_indexer.search",
            return_value=[{"filename": "a.pdf", "category": "PDFs", "snippet": "a.pdf"}],
        )
        mocker.patch(
            "src.ai.agent.generate_rag_answer",
            return_value="Found a.pdf.",
        )
        result = agent.process("find my pdfs")
        assert result["intent"] == "search_files"
        assert result["response"] == "Found a.pdf."

    def test_search_no_results_formats_message(self, mocker, _llm_online):
        mocker.patch(
            "src.ai.agent.parse_intent",
            return_value={"tool": "search", "query": "nothing", "params": {}},
        )
        mocker.patch("src.ai.agent.rag_indexer.search", return_value=[])
        result = agent.process("find nothing")
        assert result["intent"] == "search_files"
        assert "No relevant files" in result["response"]

    def test_config_tool_delegates_returning_none_response(self, mocker, _llm_online):
        """Config actions return response=None so the GUI confirm bar owns the flow."""
        mocker.patch(
            "src.ai.agent.parse_intent",
            return_value={"tool": "config", "query": "stop zip", "params": {}},
        )
        result = agent.process("stop organizing zip files")
        assert result["intent"] == "update_config"
        assert result["response"] is None

    def test_unknown_tool_falls_back_to_deterministic(self, mocker, _llm_online):
        mocker.patch(
            "src.ai.agent.parse_intent",
            return_value={"tool": "unknown", "query": "status", "params": {}},
        )
        result = agent.process("status")
        assert result["intent"] == "debug_info"
        assert result["response"] is None

    def test_greeting_tool_returns_welcome(self, mocker, _llm_online):
        mocker.patch(
            "src.ai.agent.parse_intent",
            return_value={"tool": "greeting", "query": "hello", "params": {}},
        )
        result = agent.process("hello")
        assert result["intent"] == "greeting"
        assert "FileManager assistant" in result["response"]
        assert "find" in result["response"]

    def test_llm_unavailable_falls_back_silently(self, mocker):
        mocker.patch("src.ai.llm_client.is_available", return_value=False)
        result = agent.process("find pdfs")
        # Deterministic regex picks up the search intent
        assert result["intent"] == "search_files"
        assert result["response"] is None

    def test_fresh_agent_instance_is_usable(self, mocker):
        """The exported singleton is shared, but a fresh Agent() must behave identically."""
        mocker.patch("src.ai.llm_client.is_available", return_value=False)
        fresh = Agent()
        result = fresh.process("status")
        assert result["intent"] == "debug_info"


# ---------------------------------------------------------------------------
# rag_indexer — search against a hermetic SQLite store
# Note: rag_indexer imports embed_query by reference; mock target is the name
# inside src.ai.rag_indexer.
# ---------------------------------------------------------------------------

class TestRagIndexer:
    def _seed(self, indexer, vectors):
        conn = indexer._get_conn()
        for path, vec in vectors.items():
            conn.execute(
                "INSERT OR REPLACE INTO embeddings (path, model, vector) VALUES (?, ?, ?)",
                (path, "nomic-embed-text", json.dumps(vec)),
            )
        conn.commit()
        conn.close()

    def _indexer_with_db(self, tmp_path, mocker):
        idx = RagIndexer()
        idx._db_path = str(tmp_path / "metadata.db")
        mocker.patch(
            "src.ai.rag_indexer.get_embed_model",
            return_value="nomic-embed-text",
        )
        return idx

    def test_search_ranks_by_cosine_similarity(self, tmp_path, mocker):
        idx = self._indexer_with_db(tmp_path, mocker)
        # query vector similar to the tax doc, far from the image
        self._seed(
            idx,
            {
                "/tmp/tax.pdf": [1.0, 0.0, 0.0, 0.0],
                "/tmp/photo.png": [0.0, 1.0, 1.0, 1.0],
            },
        )
        mocker.patch("src.ai.rag_indexer.embed_query", return_value=[1.0, 0.0, 0.0, 0.0])
        mocker.patch(
            "src.ai.rag_indexer.RagIndexer._get_file_info",
            side_effect=lambda p: {
                "path": p,
                "filename": p.rsplit("/", 1)[-1],
                "category": "x",
                "snippet": p.rsplit("/", 1)[-1],
            },
        )
        results = idx.search("taxes")
        assert results[0]["filename"] == "tax.pdf"
        assert results[0]["score"] > results[1]["score"]

    def test_search_empty_store_returns_empty(self, tmp_path, mocker):
        idx = self._indexer_with_db(tmp_path, mocker)
        mocker.patch("src.ai.rag_indexer.embed_query", return_value=[1.0])
        assert idx.search("anything") == []

    def test_search_embed_failure_returns_empty(self, tmp_path, mocker):
        idx = self._indexer_with_db(tmp_path, mocker)
        mocker.patch(
            "src.ai.rag_indexer.embed_query",
            side_effect=ConnectionError("down"),
        )
        assert idx.search("anything") == []


# ---------------------------------------------------------------------------
# config schema v3 — ai key lands on migration, off by default
# ---------------------------------------------------------------------------

class TestConfigSchemaV3:
    def test_schema_version_is_3(self):
        assert SCHEMA_VERSION == 3
        assert 3 in MIGRATIONS

    def test_migrate_v2_dict_gets_ai_defaults(self):
        v2 = {"schema_version": 2, "watch_directory": "/tmp/x"}
        migrated = MIGRATIONS[3](v2)
        assert migrated["ai"]["enabled"] is False
        assert migrated["ai"]["model"] == "qwen3:0.6b"
        assert migrated["ai"]["embed_model"] == "nomic-embed-text"

    def test_default_config_has_ai_off(self):
        assert DEFAULT_CONFIG["ai"]["enabled"] is False
        assert "model" in DEFAULT_CONFIG["ai"]


# ---------------------------------------------------------------------------
# chat.py wiring contract — used via reflection to avoid GUI import cost
# ---------------------------------------------------------------------------

class TestChatWiringContract:
    def test_chat_imports_optional_and_config_service(self):
        """The integration points the wiring needs are present in chat.py."""
        import inspect
        import src.gui.chat as chat_mod

        src_ = inspect.getsource(chat_mod)
        assert "from typing import Optional" in src_
        assert "from src.services.config_service import config_service" in src_
        assert "def _attempt_ai" in src_
        assert "rag_indexer.start()" in src_