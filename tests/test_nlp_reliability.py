"""
Reliability tests for the NLP Service (roadmap 4.3, ADR-011).

spaCy was removed entirely: the service is a deterministic rule engine and
must keep working with zero heavyweight dependencies — even when spaCy is
importable, it is never touched. These tests prove that invariant.
"""
import builtins
import pytest
from src.services.nlp_service import get_nlp_service


def test_nlp_deterministic_rules_mode():
    """The rule engine is the primary (and only) mode — no NLP model behind it."""
    service = get_nlp_service()

    assert service.is_fallback_mode is True
    assert service.nlp is None


def test_nlp_never_imports_spacy():
    """Even if spacy is importable, the service must never touch it."""
    real_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name == "spacy" or name.startswith("spacy."):
            raise AssertionError(f"nlp_service must not import {name}")
        return real_import(name, *args, **kwargs)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(builtins, "__import__", guarded)
        # Force a fresh instance so module init runs under the guard
        from src.services import nlp_service as ns
        ns._nlp_service_instance = None
        service = get_nlp_service()

        assert service.parse("find pdfs from today")["intent"] == "search_files"


def test_nlp_major_intents_work():
    """Search, config, cleanup intents all parse without any NLP model."""
    service = get_nlp_service()

    # Search
    res_search = service.parse("find pdfs from today")
    assert res_search["intent"] == "search_files"
    assert res_search["entities"]["extension"] == ".pdf"

    # Config
    res_config = service.parse("stop organizing zip files")
    assert res_config["intent"] == "update_config"
    assert res_config["entities"]["action"] == "toggle_monitor"

    # Cleanup
    res_cleanup = service.parse("run cleanup")
    assert res_cleanup["intent"] == "run_cleanup"

    # Stats
    res_stats = service.parse("show stats")
    assert res_stats["intent"] == "debug_info"


def test_nlp_size_and_date_entities():
    """Entity extraction (size units, dates) stays behavior-identical."""
    service = get_nlp_service()

    res = service.parse("find images larger than 5mb from last week")

    assert res["intent"] == "search_files"
    assert res["entities"]["category"] == "Images"
    assert res["entities"]["min_size"] == 5 * 1024 * 1024
    assert "date_after" in res["entities"]