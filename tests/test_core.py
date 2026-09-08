import pytest
from pathlib import Path
from src.core.classifier import Classifier
from src.core.organizer import Organizer

def test_classifier_logic():
    classifier = Classifier()
    
    # Test basic classification
    assert classifier.classify(Path("test.jpg")) == "Images"
    assert classifier.classify(Path("test.pdf")) == "PDFs"
    assert classifier.classify(Path("unknown.xyz")) == "Others"

def test_classifier_refresh_on_config_change():
    """C1: config-change callback must not raise (logger was previously missing)."""
    classifier = Classifier()
    classifier.refresh_on_config_change({})  # would NameError before the logger import fix
    assert classifier.classify(Path("test.jpg")) == "Images"

def test_organizer_rename_logic(tmp_path):
    organizer = Organizer()
    
    # Create a source file
    source = tmp_path / "test.txt"
    source.write_text("hello")
    
    # Create a collision file in target
    target_dir = tmp_path / "Documents"
    target_dir.mkdir()
    collision = target_dir / "test.txt"
    collision.write_text("existing")
    
    # Move and check for renaming
    new_path = organizer.move_file(source, target_dir)
    
    assert new_path.name == "test (1).txt"
    assert new_path.exists()
    assert collision.exists()

def test_organizer_skip_logic(tmp_path, mocker):
    # Mock config to use 'skip' strategy
    mocker.patch("src.services.config_service.config_service.get", return_value="skip")
    
    organizer = Organizer()
    source = tmp_path / "test.txt"
    source.write_text("hello")
    
    target_dir = tmp_path / "Documents"
    target_dir.mkdir()
    collision = target_dir / "test.txt"
    collision.write_text("existing")
    
    result = organizer.move_file(source, target_dir)
    assert result is None
    assert source.exists() # Should still be at source
