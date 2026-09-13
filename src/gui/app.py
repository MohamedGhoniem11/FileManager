"""
Main GUI Container
------------------
Root window for the CustomTkinter application.
Handles view switching, navigation, and global layout.
"""
import customtkinter as ctk
from src.services.config_service import config_service
from src.services.logger import logger
from src.services.db_service import db_service
from .dashboard import DashboardFrame
from .logs import LogsFrame
from .settings import SettingsFrame
from .maintenance import MaintenanceFrame
from .chat import ChatFrame
from .needs_review import NeedsReviewFrame
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
        self.logo_label.grid(row=0, column=0, padx=Theme.PAD_LG, pady=(24, 20), sticky="w")

        self.nav_buttons = {}  # name -> CTkButton
        self.nav_indicators = {}  # name -> 3px accent bar on button's left edge

        self.dashboard_btn = self._register_nav("dashboard", "Dashboard", 1)
        self.needs_review_btn = self._register_nav("needs_review", "Needs Review", 2)
        self.logs_btn = self._register_nav("logs", "Logs", 3)
        self.maintenance_btn = self._register_nav("maintenance", "Maintenance", 4)
        self.assistant_btn = self._register_nav("assistant", "Assistant", 5)

        # Settings pinned to the bottom of the sidebar (desktop-app pattern)
        self.settings_btn = self._register_nav("settings", "⚙ Settings", 7, bottom=True)

        # Main Content Frames
        self.dashboard_frame = DashboardFrame(self, corner_radius=0, fg_color="transparent")
        self.logs_frame = LogsFrame(self, corner_radius=0, fg_color="transparent")
        self.settings_frame = SettingsFrame(self, corner_radius=0, fg_color="transparent")
        self.maintenance_frame = MaintenanceFrame(self, corner_radius=0, fg_color="transparent")
        self.assistant_frame = ChatFrame(self, corner_radius=0, fg_color="transparent")
        self.needs_review_frame = NeedsReviewFrame(self, corner_radius=0, fg_color="transparent")

        # Initial Frame
        self.select_frame("dashboard")
        self.refresh_review_badge()

    def refresh_review_badge(self):
        count = db_service.count_needs_review()
        self.needs_review_btn.configure(
            text=f"Needs Review ({count})" if count else "Needs Review"
        )
        self.after(5000, self.refresh_review_badge)

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

    def _register_nav(self, name: str, text: str, row: int, bottom: bool = False) -> ctk.CTkButton:
        button = self._make_nav_button(text, name)
        pady = (0, Theme.PAD_LG) if bottom else (0, 2) if row == 1 else 2
        button.grid(row=row, column=0, padx=Theme.PAD_MD, pady=pady, sticky="ew")
        self.nav_buttons[name] = button

        indicator = ctk.CTkFrame(
            self.sidebar_frame,
            width=3,
            height=Theme.ROW_H,
            corner_radius=0,
            fg_color="transparent",
        )
        indicator.place(in_=button, x=0, y=0, relheight=1, bordermode="outside")
        self.nav_indicators[name] = indicator
        return button

    def select_frame(self, name):
        for nav_name, btn in self.nav_buttons.items():
            active = nav_name == name
            btn.configure(
                fg_color=Theme.ACCENT_SOFT if active else "transparent",
                text_color=Theme.TEXT_PRIMARY if active else Theme.TEXT_SECONDARY,
            )
            self.nav_indicators[nav_name].configure(
                fg_color=Theme.ACCENT if active else "transparent"
            )

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

        if name == "needs_review":
            self.needs_review_frame.refresh()
            self.needs_review_frame.grid(row=0, column=1, sticky="nsew")
        else:
            self.needs_review_frame.grid_forget()

def start_gui():
    ctk.set_appearance_mode("dark")
    app = App()
    app.mainloop()
