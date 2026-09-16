"""
Agent — agentic tool loop with deterministic fallback
------------------------------------------------------
LLM proposes tools, deterministic code executes.
On any LLM failure, falls back to nlp_service (deterministic regex).

ADR ref: ADR-017 (agent loop, deterministic fallback chain)
"""
from typing import Dict, Any, Callable

from src.ai import llm_client
from src.ai.assistant_llm import parse_intent, generate_rag_answer
from src.ai.rag_indexer import rag_indexer
from src.services.nlp_service import get_nlp_service
from src.services.db_service import db_service
from src.services.config_service import config_service
from src.services.logger import logger


class Agent:
    """Agentic tool loop for the Assistant.

    LLM proposes tools, deterministic code executes.
    On any LLM failure, falls back to nlp_service (deterministic regex).
    """

    def __init__(self):
        self._callbacks: Dict[str, Callable] = {}

    def register_callback(self, tool: str, callback: Callable) -> None:
        """Register a callback for a specific tool action."""
        self._callbacks[tool] = callback

    def process(self, text: str) -> Dict[str, Any]:
        """Process user message through LLM tool selection + execution.

        Returns: {"intent": ..., "entities": ..., "response": ...}
        Same shape as nlp_service.parse() for GUI compatibility.
        """
        if not llm_client.is_available():
            logger.info("LLM unavailable, falling back to deterministic NLP.")
            return self._deterministic_fallback(text)

        try:
            intent = parse_intent(text)
        except Exception as e:
            logger.warning(f"LLM intent failed: {e}")
            return self._deterministic_fallback(text)

        tool = intent.get("tool", "unknown")
        query = intent.get("query", text)

        if tool == "search":
            return self._tool_search(query)
        elif tool == "answer":
            return self._tool_answer(query)
        elif tool == "config":
            return self._tool_config(text, intent.get("params", {}))
        elif tool == "scan":
            return self._tool_scan(query)
        elif tool == "status":
            return self._tool_status()
        elif tool == "greeting":
            return self._tool_greeting()
        else:
            return self._deterministic_fallback(text)

    def _tool_search(self, query: str) -> Dict[str, Any]:
        """RAG search: embed query → retrieve → generate answer."""
        try:
            results = rag_indexer.search(query, top_k=5)

            if results:
                answer = generate_rag_answer(query, results)
                if answer:
                    return {
                        "intent": "search_files",
                        "entities": {"query": query},
                        "response": answer,
                    }
                resp = f"Found {len(results)} relevant files:\n"
                for f in results[:5]:
                    resp += f"  {f.get('filename', '?')} ({f.get('category', '?')})\n"
                return {
                    "intent": "search_files",
                    "entities": {"query": query},
                    "response": resp,
                }
            else:
                return {
                    "intent": "search_files",
                    "entities": {"query": query},
                    "response": "No relevant files found for that query.",
                }
        except Exception as e:
            logger.error(f"RAG search failed: {e}")
            return self._deterministic_fallback(query)

    def _tool_answer(self, query: str) -> Dict[str, Any]:
        """General answer (no file search needed)."""
        stats = db_service.get_stats()
        total = stats.get("total_files", 0)
        cats = stats.get("categories", {})
        resp = f"System status: {total} files indexed across {len(cats)} categories."
        if cats:
            resp += "\n" + "\n".join(f"  {k}: {v}" for k, v in cats.items())
        return {"intent": "debug_info", "entities": {}, "response": resp}

    def _tool_config(self, text: str, params: dict) -> Dict[str, Any]:
        """Route config changes through existing NLP + ConfigAgent."""
        nlp = get_nlp_service()
        result = nlp.parse(text)
        return {
            "intent": result["intent"],
            "entities": result["entities"],
            "response": None,
        }

    def _tool_scan(self, query: str) -> Dict[str, Any]:
        """Trigger scan — route through existing NLP."""
        nlp = get_nlp_service()
        scan_text = query if "scan" in query.lower() else f"scan {query}"
        result = nlp.parse(scan_text)
        return {
            "intent": result["intent"],
            "entities": result["entities"],
            "response": None,
        }

    def _tool_status(self) -> Dict[str, Any]:
        """System status."""
        stats = db_service.get_stats()
        if "error" in stats:
            return {
                "intent": "debug_info",
                "entities": {},
                "response": f"Error: {stats['error']}",
            }
        resp = f"System Status:\n  Files indexed: {stats['total_files']}\n"
        for cat, count in stats.get("categories", {}).items():
            resp += f"  {cat}: {count}\n"
        return {"intent": "debug_info", "entities": {}, "response": resp}

    def _tool_greeting(self) -> Dict[str, Any]:
        """Greeting / help response."""
        stats = db_service.get_stats()
        total = stats.get("total_files", 0)
        resp = (
            f"Hi! I'm your FileManager assistant. I can see {total} files in your library.\n\n"
            "Try asking me to:\n"
            "  \u2022 find images, PDFs, or any file type\n"
            "  \u2022 show system status and stats\n"
            "  \u2022 scan for new files\n"
            "  \u2022 change settings (e.g. stop organizing zip files)\n\n"
            "Just type naturally \u2014 I'll figure out what you mean."
        )
        return {"intent": "greeting", "entities": {}, "response": resp}

    def _deterministic_fallback(self, text: str) -> Dict[str, Any]:
        """Fallback to nlp_service when LLM is unavailable."""
        nlp = get_nlp_service()
        result = nlp.parse(text)
        return {
            "intent": result["intent"],
            "entities": result["entities"],
            "response": None,
        }


# Module-level singleton
agent = Agent()
