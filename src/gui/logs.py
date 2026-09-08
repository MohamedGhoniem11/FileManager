"""
Log View Component
------------------
Scrollable log display integrated with the system's queue handler.
"""
import customtkinter as ctk
from src.services.logger import logger, log_queue
from .theme import Theme
import queue

class LogsFrame(ctk.CTkFrame):
    """Displays real-time application logs for administrative monitoring."""
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            self,
            text="Application Logs",
            text_color=Theme.TEXT_PRIMARY,
            font=ctk.CTkFont(size=Theme.FONT_H2_SIZE, weight="bold"),
        ).grid(row=0, column=0, padx=Theme.PAD_LG, pady=(24, Theme.PAD_LG), sticky="w")
        
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
        self.textbox.grid(row=1, column=0, padx=Theme.PAD_LG, pady=(0, Theme.PAD_LG), sticky="nsew")
        
        self.after(100, self.update_logs)

    def update_logs(self):
        """Processes logs from the queue and displays them."""
        while not log_queue.empty():
            try:
                record = log_queue.get_nowait()
                msg = f"{record.levelname}: {record.getMessage()}\n"
                
                self.textbox.configure(state="normal")
                self.textbox.insert("end", msg)
                self.textbox.see("end")
                self.textbox.configure(state="disabled")
            except queue.Empty:
                break
        
        self.after(100, self.update_logs)