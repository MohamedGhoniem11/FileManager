from pathlib import Path
from typing import Dict, List
"""
Classification Engine
---------------------
Logic for mapping file extensions to user-defined categories.
"""
import os
from src.services.config_service import config_service
from src.services.logger import logger

class Classifier:
    """Handles the categorization of files based on their extensions and configuration."""
    
    def __init__(self):
        self.refresh_mappings()
        config_service.register_callback(self.refresh_on_config_change)

    def refresh_on_config_change(self, new_config: dict):
        logger.info("Classifier refreshing categories due to config change.")
        self.refresh_mappings()

    def refresh_mappings(self):
        """Reloads categories from the config service."""
        raw_categories = config_service.get_categories()
        # Flatten for faster lookup: {ext: category}
        self.extension_map: Dict[str, str] = {}
        for category, extensions in raw_categories.items():
            for ext in extensions:
                self.extension_map[ext.lower()] = category

    def classify(self, file_path: Path) -> str:
        """Returns the category for a given file path based on its extension."""
        extension = file_path.suffix.lower()
        return self.extension_map.get(extension, "Others")

classifier = Classifier()
