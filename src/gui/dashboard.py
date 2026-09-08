"""
Dashboard View
--------------
Primary status overview showing service state and current watch directory.
"""
import customtkinter as ctk
from src.services.observer import observer_service
from src.services.config_service import config_service
from src.services.logger import logger
from .theme import Theme

class DashboardFrame(ctk.CTkFrame):
    """Visual representation of system health and real-time monitor status."""
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        self.grid_columnconfigure(0, weight=1)
        
        # Title
        ctk.CTkLabel(
            self,
            text="System Dashboard",
            text_color=Theme.TEXT_PRIMARY,
            font=ctk.CTkFont(size=Theme.FONT_H1_SIZE, weight="bold"),
        ).grid(row=0, column=0, padx=Theme.PAD_LG, pady=(24, Theme.PAD_LG), sticky="w")
        
        # Status Card
        self.status_frame = ctk.CTkFrame(
            self,
            fg_color=Theme.BG_ELEVATED,
            corner_radius=Theme.RADIUS_LG,
            border_width=1,
            border_color=Theme.BORDER,
        )
        self.status_frame.grid(row=1, column=0, padx=Theme.PAD_LG, pady=Theme.PAD_MD, sticky="ew")
        self.status_frame.grid_columnconfigure(1, weight=1)
        
        self.status_dot = ctk.CTkLabel(self.status_frame, text="●", text_color=Theme.NEUTRAL, font=ctk.CTkFont(size=Theme.FONT_BODY_SIZE))
        self.status_dot.grid(row=0, column=0, padx=(Theme.PAD_LG, Theme.PAD_SM), pady=Theme.PAD_MD)
        
        self.status_label = ctk.CTkLabel(
            self.status_frame,
            text="Status: INACTIVE",
            text_color=Theme.TEXT_PRIMARY,
            font=ctk.CTkFont(size=Theme.FONT_BODY_SIZE),
        )
        self.status_label.grid(row=0, column=1, padx=(0, Theme.PAD_LG), pady=Theme.PAD_MD, sticky="w")
        
        # Control Buttons
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.grid(row=2, column=0, padx=Theme.PAD_LG, pady=Theme.PAD_LG, sticky="w")
        
        self.start_btn = ctk.CTkButton(
            self.btn_frame,
            text="Start Monitor",
            command=self.toggle_monitor,
            fg_color=Theme.ACCENT,
            hover_color=Theme.ACCENT_HOVER,
            height=Theme.BTN_H,
            corner_radius=Theme.RADIUS_MD,
            font=ctk.CTkFont(size=Theme.FONT_BODY_SIZE),
        )
        self.start_btn.grid(row=0, column=0, padx=(0, Theme.PAD_MD))
        
        self.info_label = ctk.CTkLabel(
            self,
            text=f"Watching: {config_service.get('watch_directory')}",
            text_color=Theme.TEXT_MUTED,
            font=ctk.CTkFont(size=Theme.FONT_SMALL_SIZE, slant="italic"),
        )
        self.info_label.grid(row=3, column=0, padx=Theme.PAD_LG, pady=Theme.PAD_SM, sticky="w")
        
        # Additional Settings
        self.settings_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.settings_frame.grid(row=4, column=0, padx=Theme.PAD_LG, pady=Theme.PAD_MD, sticky="w")
        
        from src.services.startup_service import startup_service
        self.startup_var = ctk.BooleanVar(value=startup_service.is_enabled())
        
        self.startup_switch = ctk.CTkSwitch(
            self.settings_frame, 
            text="Run on Windows Startup", 
            command=self.toggle_startup,
            variable=self.startup_var,
            progress_color=Theme.ACCENT,
            text_color=Theme.TEXT_SECONDARY,
        )
        self.startup_switch.grid(row=0, column=0)

        self.update_status()

    def toggle_startup(self):
        from src.services.startup_service import startup_service
        from src.services.config_service import config_service
        
        if self.startup_var.get():
            startup_service.enable_startup()
            logger.info("Startup enabled via dashboard.")
        else:
            startup_service.disable_startup()
            logger.info("Startup disabled via dashboard.")
            
        # Persist preference
        auto = config_service.get("automation", {}).copy()
        auto["run_on_startup"] = self.startup_var.get()
        config_service.save_config({"automation": auto})

    def toggle_monitor(self):
        if observer_service.is_running:
            observer_service.stop()
            logger.info("Monitor stopped manually via dashboard.")
        else:
            observer_service.start()
            logger.info("Monitor started manually via dashboard.")
        self.update_status()

    def update_status(self):
        if observer_service.is_running:
            self.status_dot.configure(text_color=Theme.SUCCESS)
            self.status_label.configure(text="Status: ACTIVE", text_color=Theme.SUCCESS)
            self.start_btn.configure(text="Stop Monitor")
        else:
            self.status_dot.configure(text_color=Theme.NEUTRAL)
            self.status_label.configure(text="Status: INACTIVE", text_color=Theme.TEXT_PRIMARY)
            self.start_btn.configure(text="Start Monitor")
        
        self.info_label.configure(text=f"Watching: {config_service.get('watch_directory')}")
        self.after(1000, self.update_status)
