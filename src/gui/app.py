"""
Main GUI Container
------------------
Root window for the CustomTkinter application.
Handles view switching, navigation, and global layout.
"""
import customtkinter as ctk
from src.services.config_service import config_service
from src.services.logger import logger
from .dashboard import DashboardFrame
from .logs import LogsFrame
from .settings import SettingsFrame
from .maintenance import MaintenanceFrame
from .chat import ChatFrame
from .theme import Theme

class App(ctk.CTk):
    """Main application window container and navigation controller."""
    def __init__(self):
        super().__init__()

        # Window Setup
        self.title("Standard File Manager - Pro Edition")
        self.geometry(config_service.get("gui_preferences", {}).get("window_size", "1000x600"))
        
        # Grid layout (1x2)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        self.sidebar_frame = ctk.CTkFrame(self, width=180, corner_radius=0, fg_color=Theme.BG_DEEP)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(6, weight=1)
        self.sidebar_frame.grid_propagate(False)

        self.logo_label = ctk.CTkLabel(
            self.sidebar_frame,
            text="FileManager",
            text_color=Theme.TEXT_PRIMARY,
            font=ctk.CTkFont(size=Theme.FONT_H1_SIZE, weight="bold"),
        )
        self.logo_label.grid(row=0, column=0, padx=Theme.PAD_LG, pady=(24, 20))

        self.dashboard_btn = self._make_nav_button("Dashboard", "dashboard")
        self.dashboard_btn.grid(row=1, column=0, padx=Theme.PAD_MD, pady=(0, 2), sticky="ew")

        self.logs_btn = self._make_nav_button("Logs", "logs")
        self.logs_btn.grid(row=2, column=0, padx=Theme.PAD_MD, pady=2, sticky="ew")

        self.settings_btn = self._make_nav_button("Settings", "settings")
        self.settings_btn.grid(row=3, column=0, padx=Theme.PAD_MD, pady=2, sticky="ew")

        self.maintenance_btn = self._make_nav_button("Maintenance", "maintenance")
        self.maintenance_btn.grid(row=4, column=0, padx=Theme.PAD_MD, pady=2, sticky="ew")

        self.assistant_btn = self._make_nav_button("Assistant", "assistant")
        self.assistant_btn.grid(row=5, column=0, padx=Theme.PAD_MD, pady=(2, 0), sticky="ew")

        self.version_label = ctk.CTkLabel(
            self.sidebar_frame,
            text="Standard File Manager — Pro Edition",
            text_color=Theme.TEXT_MUTED,
            font=ctk.CTkFont(size=Theme.FONT_SMALL_SIZE - 2),
        )
        self.version_label.grid(row=7, column=0, padx=Theme.PAD_LG, pady=(0, 16))

        # Main Content Frames
        self.dashboard_frame = DashboardFrame(self, corner_radius=0, fg_color="transparent")
        self.logs_frame = LogsFrame(self, corner_radius=0, fg_color="transparent")
        self.settings_frame = SettingsFrame(self, corner_radius=0, fg_color="transparent")
        self.maintenance_frame = MaintenanceFrame(self, corner_radius=0, fg_color="transparent")
        self.assistant_frame = ChatFrame(self, corner_radius=0, fg_color="transparent")

        # Initial Frame
        self.select_frame("dashboard")

    def _make_nav_button(self, text: str, frame_name: str) -> ctk.CTkButton:
        return ctk.CTkButton(
            self.sidebar_frame,
            text=text,
            command=lambda: self.select_frame(frame_name),
            corner_radius=Theme.RADIUS_MD,
            height=Theme.ROW_H,
            border_spacing=Theme.PAD_MD,
            fg_color="transparent",
            text_color=Theme.TEXT_SECONDARY,
            hover_color=Theme.BG_RAISED,
            anchor="w",
            font=ctk.CTkFont(size=Theme.FONT_BODY_SIZE),
        )

    def select_frame(self, name):
        # Reset button colors
        self.dashboard_btn.configure(fg_color=Theme.ACCENT_SOFT if name == "dashboard" else "transparent")
        self.dashboard_btn.configure(text_color=Theme.TEXT_PRIMARY if name == "dashboard" else Theme.TEXT_SECONDARY)
        self.logs_btn.configure(fg_color=Theme.ACCENT_SOFT if name == "logs" else "transparent")
        self.logs_btn.configure(text_color=Theme.TEXT_PRIMARY if name == "logs" else Theme.TEXT_SECONDARY)
        self.settings_btn.configure(fg_color=Theme.ACCENT_SOFT if name == "settings" else "transparent")
        self.settings_btn.configure(text_color=Theme.TEXT_PRIMARY if name == "settings" else Theme.TEXT_SECONDARY)
        self.maintenance_btn.configure(fg_color=Theme.ACCENT_SOFT if name == "maintenance" else "transparent")
        self.maintenance_btn.configure(text_color=Theme.TEXT_PRIMARY if name == "maintenance" else Theme.TEXT_SECONDARY)
        self.assistant_btn.configure(fg_color=Theme.ACCENT_SOFT if name == "assistant" else "transparent")
        self.assistant_btn.configure(text_color=Theme.TEXT_PRIMARY if name == "assistant" else Theme.TEXT_SECONDARY)

        # Show selected frame
        if name == "dashboard":
            self.dashboard_frame.grid(row=0, column=1, sticky="nsew")
        else:
            self.dashboard_frame.grid_forget()
            
        if name == "logs":
            self.logs_frame.grid(row=0, column=1, sticky="nsew")
        else:
            self.logs_frame.grid_forget()
            
        if name == "settings":
            self.settings_frame.grid(row=0, column=1, sticky="nsew")
        else:
            self.settings_frame.grid_forget()

        if name == "maintenance":
            self.maintenance_frame.grid(row=0, column=1, sticky="nsew")
        else:
            self.maintenance_frame.grid_forget()

        if name == "assistant":
            self.assistant_frame.grid(row=0, column=1, sticky="nsew")
        else:
            self.assistant_frame.grid_forget()

def start_gui():
    ctk.set_appearance_mode("dark")
    app = App()
    app.mainloop()
