"""
Unit tests for the Intelligent Assistant Layer.
Covers NLP intent detection, entity parsing, and SQLite indexing integrity.
"""
import pytest
from pathlib import Path
from src.services.nlp_service import get_nlp_service
from src.services.db_service import db_service
from src.core.config_agent import config_agent

nlp_service = get_nlp_service()

def test_nlp_search_intent():
    """Verifies that search queries are correctly parsed."""
    query = "find pdfs larger than 5mb from today"
    result = nlp_service.parse(query)
    
    assert result["intent"] == "search_files"
    assert result["entities"]["extension"] == ".pdf"
    assert result["entities"]["min_size"] == 5 * 1024 * 1024
    assert "date_after" in result["entities"]

def test_nlp_config_intent():
    """Verifies that config commands are correctly parsed."""
    query = "stop organizing zip files"
    result = nlp_service.parse(query)
    
    # "stop" defaults to toggle_monitor False in my simple rule engine
    assert result["intent"] == "update_config"
    assert result["entities"]["action"] == "toggle_monitor"
    assert result["entities"]["value"] is False

def test_config_agent_validation():
    """Verifies that the config agent provides safe proposals."""
    entities = {"action": "set_interval", "value": 30}
    valid, desc, patch = config_agent.validate_and_propose(entities)
    
    assert valid is True
    assert "30 minutes" in desc
    assert patch["automation"]["auto_scan_interval_min"] == 30

def test_db_indexing(tmp_path):
    """Verifies that the database service correctly indexes file entries."""
    # Use a temporary DB for testing
    test_db = tmp_path / "test_metadata.db"
    from src.services.db_service import DbService
    db = DbService(str(test_db))
    
    # create a dummy file
    dummy_file = tmp_path / "test.txt"
    dummy_file.write_text("hello world")
    
    db.upsert_file(dummy_file)
    
    # Query it back
    results = db.query_files({"extension": ".txt"})
    assert len(results) == 1
    assert results[0]["filename"] == "test.txt"
    
    # Remove it
    db.remove_file(dummy_file)
    results = db.query_files({"extension": ".txt"})
    assert len(results) == 0
