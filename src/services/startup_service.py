import os
import sys
from pathlib import Path
from src.services.logger import logger

try:
    import winshell
    from win32com.client import Dispatch  # type: ignore
    _WINDOWS_AVAILABLE = True
except ImportError:
    winshell = None
    Dispatch = None
    _WINDOWS_AVAILABLE = False

# Tracks whether non-frozen dev mode can map back to main.py
_HAS_MAIN_INFO = hasattr(sys.modules.get('__main__', None), '__file__')

class StartupService:
    """
    Manages the application's auto-startup entry on Windows.
    Uses the user's Startup folder (shell:startup) to avoid needing Admin privileges.
    On non-Windows platforms, all operations are safe no-ops.
    """

    def __init__(self):
        if not _WINDOWS_AVAILABLE:
            logger.warning("StartupService requires Windows; operations disabled.")
        self.startup_dir = Path(winshell.startup()) if winshell else None
        self.link_path = self.startup_dir / "FileManagerPro.lnk" if self.startup_dir else None
        self.executable_path = sys.executable if getattr(sys, 'frozen', False) else None
        self.script_path = str(Path(sys.modules['__main__'].__file__).parent.parent / "main.py") if not self.executable_path and _HAS_MAIN_INFO else None
        
        # Determine target: The EXE if frozen, else pythonw.exe running main.py
        if getattr(sys, 'frozen', False):
            self.target = sys.executable
            self.args = ""
            self.cwd = str(Path(sys.executable).parent)
        else:
            # Development mode: Run using pythonw.exe to avoid console window
            self.target = sys.executable.replace("python.exe", "pythonw.exe")
            # We need to point to the main module
            # Best effort assumption for dev mode
            self.cwd = os.getcwd()
            self.args = f"-m src.main"

    def is_enabled(self) -> bool:
        """Checks if the startup shortcut exists."""
        return bool(self.link_path) and self.link_path.exists()

    def enable_startup(self):
        """Creates a shortcut in the Windows Startup folder."""
        if not _WINDOWS_AVAILABLE or not self.startup_dir:
            return
        try:
            shell = Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(str(self.link_path))
            shortcut.Targetpath = self.target
            shortcut.WorkingDirectory = self.cwd
            shortcut.Arguments = self.args
            shortcut.Description = "File Manager Pro Auto-Startup"
            shortcut.save()
            logger.info(f"Startup shortcut created at {self.link_path}")
        except Exception as e:
            logger.error(f"Failed to enable startup: {e}")

    def disable_startup(self):
        """Removes the shortcut from the Windows Startup folder."""
        if not _WINDOWS_AVAILABLE or not self.link_path:
            return
        try:
            if self.link_path.exists():
                os.remove(self.link_path)
                logger.info("Startup shortcut removed.")
        except Exception as e:
            logger.error(f"Failed to disable startup: {e}")

startup_service = StartupService()
