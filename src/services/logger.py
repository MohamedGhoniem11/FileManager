import logging
"""
Logging Infrastructure
---------------------
Setup for dual-output logging (console and file) with queue support for GUI integration.
"""
import logging.handlers
import sys
import os
import queue
from pathlib import Path

import platformdirs

def default_log_path(log_file: str) -> Path:
    """Log home resolves via platformdirs (ADR-014/H4); FILEMANAGER_LOG_DIR overrides."""
    override = os.environ.get("FILEMANAGER_LOG_DIR")
    if override:
        return Path(override) / log_file
    return Path(platformdirs.user_log_dir("FileManager")) / log_file

def setup_logger(name: str = "filemanager", log_file: str = "app.log") -> logging.Logger:
    """Sets up a dual-output logger (console + file)."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Avoid duplicate handlers if setup is called multiple times
    if not logger.handlers:
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Console Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # File Handler
        try:
            log_path = default_log_path(log_file)
            log_path.parent.mkdir(exist_ok=True)
            file_handler = logging.FileHandler(log_path)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception:
            # Fallback to console only if file logging fails
            pass

        # Queue Handler for GUI
        log_queue = queue.Queue()
        queue_handler = logging.handlers.QueueHandler(log_queue)
        logger.addHandler(queue_handler)

    return logger

logger = setup_logger()
# Extract the queue from the QueueHandler if it exists
def _get_log_queue():
    for handler in logger.handlers:
        if isinstance(handler, logging.handlers.QueueHandler):
            return handler.queue
    return None

log_queue = _get_log_queue()
