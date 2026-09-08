"""
Log View Component
------------------
Scrollable log display integrated with the system's queue handler.
Log lines are colorized by level; a rotating tips bar surfaces
context-aware suggestions when the stream is quiet.
"""
import customtkinter as ctk
from src.services.logger import logger, log_queue
from src.services.config_service import config_service
from .theme import Theme
import queue
import time

TIPS = [
    "Tip: ask the Assistant 'find my pdfs' to search indexed files.",
    "Tip: run a Health Audit from Maintenance to spot duplicates and orphans.",
    "Tip: enable Scheduled Scans in Settings for hands-off keeping of folders.",
    "Tip: 'rename' collision strategy keeps every file — conflicts get a unique suffix.",
    "Tip: Safe Mode is on by default — cleanup previews results and deletes nothing.",
]

class LogsFrame(ctk.CTkFrame):
    """Displays real-time application logs for administrative monitoring."""
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._tip_index = 0
        self._last_log_time = time.time()

        ctk.CTkLabel(
            self,
            text="Application Logs",
            text_color=Theme.TEXT_PRIMARY,
            font=ctk.CTkFont(size=Theme.FONT_H2_SIZE, weight="bold"),
        ).grid(row=0, column=0, padx=Theme.PAD_LG, pady=(24, Theme.PAD_MD), sticky="w")

        self.tip_label = ctk.CTkLabel(
            self,
            text="",
            text_color=Theme.INFO,
            font=ctk.CTkFont(size=Theme.FONT_SMALL_SIZE),
            anchor="w",
        )
        self.tip_label.grid(row=1, column=0, padx=Theme.PAD_LG, pady=(0, Theme.PAD_SM), sticky="ew")

        self._create_textbox()

        self.after(100, self.update_logs)
        self.after(15000, self._rotate_tip)

    def _create_textbox(self):
        self.textbox = ctk.CTkTextbox(
            self,
            state="disabled",
            fg_color=Theme.BG_DEEP,
            text_color=Theme.TEXT_SECONDARY,
            border_width=1,
            border_color=Theme.BORDER,
            corner_radius=Theme.RADIUS_MD,
            font=ctk.CTkFont(family=Theme.FONT_MONO, size=Theme.FONT_SMALL_SIZE),
        )
        self.textbox.grid(row=2, column=0, padx=Theme.PAD_LG, pady=(0, Theme.PAD_LG), sticky="nsew")

        self.textbox.tag_config("LEVEL_DEBUG", foreground=Theme.TEXT_MUTED)
        self.textbox.tag_config("LEVEL_INFO", foreground=Theme.TEXT_SECONDARY)
        self.textbox.tag_config("LEVEL_WARNING", foreground=Theme.WARNING)
        self.textbox.tag_config("LEVEL_ERROR", foreground=Theme.ERROR)

    def _rotate_tip(self):
        monitor_enabled = config_service.get("monitor_enabled", True)
        tips = TIPS[:]
        if not monitor_enabled:
            tips.append("Hint: real-time monitoring is off — enable it in Settings.")
        dirty = (time.time() - self._last_log_time) > 45
        if dirty:
            tips.append("Hint: no recent activity — is the monitor running on the Dashboard?")
        self.tip_label.configure(text=tips[self._tip_index % len(tips)])
        self._tip_index += 1
        self.after(15000, self._rotate_tip)

    def update_logs(self):
        """Processes logs from the queue and displays them with level colorization."""
        while not log_queue.empty():
            try:
                record = log_queue.get_nowait()
                msg = f"{record.levelname}: {record.getMessage()}\n"
                tag = f"LEVEL_{record.levelname.upper()}"
                if tag not in {"LEVEL_DEBUG", "LEVEL_INFO", "LEVEL_WARNING", "LEVEL_ERROR"}:
                    tag = "LEVEL_INFO"

                self.textbox.configure(state="normal")
                self.textbox.insert("end", msg, tag)
                self.textbox.see("end")
                self.textbox.configure(state="disabled")
                self._last_log_time = time.time()
            except queue.Empty:
                break
        
        self.after(100, self.update_logs)