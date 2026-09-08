"""
Path Utilities
--------------
Helper functions for normalizing and sanitizing file system paths.
"""
import re
from pathlib import Path

def sanitize_filename(filename: str) -> str:
    """Removes illegal characters from a filename for cross-platform safety."""
    return re.sub(r'[<>:"/\\|?*]', '_', filename)
