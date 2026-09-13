"""
FileManager Pro - Main Entry Point
----------------------------------
Orchestrates the lifecycle of the file manager application, including
service initialization, background monitoring, and GUI launching.
"""
import sys
from src.services.logger import logger
from src.services.config_service import config_service
from src.services.observer import observer_service
from src.services.health_service import health_service
from src.gui.app import start_gui
import threading
import time
import multiprocessing

def engine_worker():
    """Background worker to check for config updates if the GUI is running."""
    while True:
        config_service.check_for_updates()
        time.sleep(2)

def log_excepthook(exc_type, exc_value, exc_tb):
    logger.critical(
        f"Unhandled exception: {exc_type.__name__}: {exc_value}",
        exc_info=(exc_type, exc_value, exc_tb),
    )

def log_thread_exception(args):
    logger.critical(
        f"Unhandled exception in thread '{args.thread.name}': "
        f"{args.exc_type.__name__}: {args.exc_value}",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )

def main():
    multiprocessing.freeze_support()
    sys.excepthook = log_excepthook
    threading.excepthook = log_thread_exception
    logger.info("Starting File Manager Pro...")
    
    # Auto-start observer if enabled in config
    if config_service.get("monitor_enabled", True):
        observer_service.start()
    
    # Register observer to restart when config changes
    config_service.register_callback(observer_service.restart_if_needed)
    
    # Start config watcher in background thread
    config_thread = threading.Thread(target=engine_worker, daemon=True)
    config_thread.start()

    # Start health auto-maintenance thread
    maintenance_thread = threading.Thread(target=health_service.run_auto_maintenance, daemon=True)
    maintenance_thread.start()

    # Optionally run audit on startup
    if config_service.get("automation", {}).get("run_on_startup", True):
        threading.Thread(target=health_service.run_audit, daemon=True).start()
    
    try:
        # Launch GUI
        start_gui()
    except Exception as e:
        logger.critical(f"GUI Error: {e}")
    finally:
        observer_service.stop()

if __name__ == "__main__":
    main()
