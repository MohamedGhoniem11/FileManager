"""
Settings View
-------------
Configuration interface for modifying application parameters such as
watch directory, monitoring status, and collision strategies.
"""
import customtkinter as ctk
from src.services.config_service import config_service
from src.services.logger import logger
from .theme import Theme

class SettingsFrame(ctk.CTkFrame):
    """User interface for persistent application configuration management."""
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        self.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(
            self,
            text="Configuration Settings",
            text_color=Theme.TEXT_PRIMARY,
            font=ctk.CTkFont(size=Theme.FONT_H1_SIZE, weight="bold"),
        ).grid(row=0, column=0, padx=Theme.PAD_LG, pady=(24, Theme.PAD_LG), sticky="w")
        
        # Settings Card
        card = ctk.CTkFrame(
            self,
            fg_color=Theme.BG_ELEVATED,
            corner_radius=Theme.RADIUS_LG,
            border_width=1,
            border_color=Theme.BORDER,
        )
        card.grid(row=1, column=0, padx=Theme.PAD_LG, pady=Theme.PAD_MD, sticky="ew")
        card.grid_columnconfigure(0, weight=1)
        
        # Watch Directory
        ctk.CTkLabel(
            card,
            text="Watch Directory:",
            text_color=Theme.TEXT_SECONDARY,
            font=ctk.CTkFont(size=Theme.FONT_SMALL_SIZE),
        ).grid(row=0, column=0, padx=Theme.PAD_LG, pady=(Theme.PAD_LG, Theme.PAD_SM), sticky="w")
        self.watch_dir_entry = ctk.CTkEntry(
            card,
            width=400,
            fg_color=Theme.BG_MAIN,
            border_color=Theme.BORDER,
            text_color=Theme.TEXT_PRIMARY,
            height=Theme.INPUT_H,
        )
        self.watch_dir_entry.insert(0, config_service.get("watch_directory", ""))
        self.watch_dir_entry.grid(row=1, column=0, padx=Theme.PAD_LG, pady=(0, Theme.PAD_SM), sticky="w")
        
        # Monitor Toggle
        self.monitor_var = ctk.BooleanVar(value=config_service.get("monitor_enabled", True))
        self.monitor_switch = ctk.CTkSwitch(
            card,
            text="Enable Real-time Monitoring",
            variable=self.monitor_var,
            progress_color=Theme.ACCENT,
            text_color=Theme.TEXT_SECONDARY,
        )
        self.monitor_switch.grid(row=2, column=0, padx=Theme.PAD_LG, pady=Theme.PAD_MD, sticky="w")
        
        # Collision Strategy
        ctk.CTkLabel(
            card,
            text="Collision Strategy:",
            text_color=Theme.TEXT_SECONDARY,
            font=ctk.CTkFont(size=Theme.FONT_SMALL_SIZE),
        ).grid(row=3, column=0, padx=Theme.PAD_LG, pady=(Theme.PAD_SM, Theme.PAD_SM), sticky="w")
        self.strategy_option = ctk.CTkOptionMenu(
            card,
            values=["rename", "skip", "overwrite"],
            fg_color=Theme.BG_RAISED,
            button_color=Theme.ACCENT_DARK,
            button_hover_color=Theme.ACCENT,
            text_color=Theme.TEXT_PRIMARY,
            dropdown_fg_color=Theme.BG_ELEVATED,
            dropdown_hover_color=Theme.BG_RAISED,
            dropdown_text_color=Theme.TEXT_PRIMARY,
        )
        self.strategy_option.set(config_service.get("collision_strategy", "rename"))
        self.strategy_option.grid(row=4, column=0, padx=Theme.PAD_LG, pady=(0, Theme.PAD_MD), sticky="w")
        
        # Save Button
        self.save_button = ctk.CTkButton(
            self,
            text="Save Settings",
            command=self.save_settings,
            fg_color="transparent",
            border_width=1,
            border_color=Theme.BORDER_LIGHT,
            hover_color=Theme.BG_RAISED,
            text_color=Theme.TEXT_PRIMARY,
            height=Theme.BTN_H,
            corner_radius=Theme.RADIUS_MD,
            font=ctk.CTkFont(size=Theme.FONT_BODY_SIZE),
        )
        self.save_button.grid(row=2, column=0, padx=Theme.PAD_LG, pady=Theme.PAD_LG, sticky="w")

    def save_settings(self):
        new_config = config_service.config.copy()
        new_config["watch_directory"] = self.watch_dir_entry.get()
        new_config["monitor_enabled"] = self.monitor_var.get()
        new_config["collision_strategy"] = self.strategy_option.get()
        
        config_service.save_config(new_config)
        logger.info("Settings saved via GUI")