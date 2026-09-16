"""
Assistant LLM — prompt → structured tool intent JSON
-----------------------------------------------------
Single LLM call converts user text into a structured intent object
that the agent loop can dispatch. Falls back to 'unknown' on any failure.

ADR ref: ADR-017 (tool routing, prompt design)
"""
import json
from typing import Dict, Any, List

from src.ai import llm_client
from src.services.config_service import config_service
from src.services.db_service import db_service
from src.services.logger import logger

TOOL_PROMPT = """You are a file manager assistant. Pick the BEST tool for the user's message.
Reply with ONLY a JSON object — no explanation, no markdown.

Tools:
- search: Find files by name, type, extension, date, or content keywords. ANY mention of files, docs, images, PDFs, photos → search.
- status: Show how many files are indexed, system health, stats. ANY question about counts, indexed, status, how many → status.
- scan: Trigger a file scan. ONLY when user says scan, check for new files, refresh, reindex.
- config: Change settings. ONLY when user says stop/change/enable/disable a setting or behavior.
- greeting: Say hello, introduce yourself, or say what you can do. Hi, hello, hey, help, what can you do, who are you.
- unknown: Only when nothing else fits.

Examples:
User: "find my tax documents" → {{"tool": "search", "query": "tax documents", "params": {{}}}}
User: "show me all PDFs from last week" → {{"tool": "search", "query": "PDFs last week", "params": {{}}}}
User: "how many images do I have" → {{"tool": "status", "query": "images count", "params": {{}}}}
User: "scan Downloads folder" → {{"tool": "scan", "query": "/home/dingo/Downloads", "params": {{}}}}
User: "stop organizing zip files" → {{"tool": "config", "query": "stop organizing zip files", "params": {{}}}}
User: "hello" → {{"tool": "greeting", "query": "hello", "params": {{}}}}
User: "what can you do" → {{"tool": "greeting", "query": "capabilities", "params": {{}}}}

User message: {message}

System context:
- Total indexed files: {total_files}
- Categories: {categories}
- Watch directory: {watch_dir}
"""


def get_model() -> str:
    """Returns configured chat model name."""
    ai_cfg = config_service.get("ai", {})
    if isinstance(ai_cfg, dict):
        return ai_cfg.get("model", "qwen3:0.6b")
    return "qwen3:0.6b"


def parse_intent(text: str) -> Dict[str, Any]:
    """Send user text to LLM, return structured tool intent.

    Returns: {"tool": "search|answer|config|scan|status|unknown",
              "query": "...", "params": {}}
    """
    stats = db_service.get_stats()
    total_files = stats.get("total_files", 0)
    categories = ", ".join(stats.get("categories", {}).keys()) or "none"
    watch_dir = config_service.get("watch_directory", "~/Downloads")

    prompt = TOOL_PROMPT.format(
        message=text,
        total_files=total_files,
        categories=categories,
        watch_dir=watch_dir,
    )

    try:
        model = get_model()
        response = llm_client.chat(model, prompt, think=False, timeout_s=15)
        parsed = json.loads(response)
        if "tool" not in parsed:
            parsed["tool"] = "unknown"
        if "query" not in parsed:
            parsed["query"] = text
        if "params" not in parsed:
            parsed["params"] = {}
        logger.info(f"LLM intent: {parsed['tool']} (query={parsed.get('query', '')[:50]})")
        return parsed
    except Exception as e:
        logger.warning(f"LLM intent parse failed: {e}")
        return {"tool": "unknown", "query": text, "params": {}}


def generate_rag_answer(query: str, context_files: List[Dict]) -> str:
    """Generate a natural-language answer from RAG context."""
    if not context_files:
        return ""

    context_lines = []
    for f in context_files:
        context_lines.append(
            f"- {f.get('filename', '?')} ({f.get('category', '?')}): {f.get('snippet', '')}"
        )
    context = "\n".join(context_lines)

    prompt = (
        f"Answer the user's question about their files using ONLY the information below.\n"
        f"Cite specific filenames. If the files don't contain enough info, say so.\n\n"
        f"Files found:\n{context}\n\n"
        f"Question: {query}\n\n"
        f"Answer (2-3 sentences):"
    )

    try:
        model = get_model()
        response = llm_client.chat(model, prompt, think=False, timeout_s=20)
        return response.strip()
    except Exception as e:
        logger.warning(f"RAG answer generation failed: {e}")
        return ""
