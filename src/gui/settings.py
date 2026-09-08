"""
Settings View
-------------
Configuration interface for modifying application parameters such as
watch directory, monitoring status, collision strategies, automation,
logging verbosity, and cleanup behavior.
"""
import logging
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

        self._build_watch_card()
        self._build_automation_card()
        self._build_logging_card()
        self._build_cleanup_card()

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
        self.save_button.grid(row=9, column=0, padx=Theme.PAD_LG, pady=Theme.PAD_LG, sticky="w")

    def _section_label(self, parent, row, text):
        label = ctk.CTkLabel(
            parent,
            text=text,
            text_color=Theme.TEXT_SECONDARY,
            font=ctk.CTkFont(size=Theme.FONT_SMALL_SIZE),
        )
        label.grid(row=row, column=0, padx=Theme.PAD_LG, pady=(Theme.PAD_LG, Theme.PAD_SM), sticky="w")
        return label

    def _card(self, row):
        card = ctk.CTkFrame(
            self,
            fg_color=Theme.BG_ELEVATED,
            corner_radius=Theme.RADIUS_LG,
            border_width=1,
            border_color=Theme.BORDER,
        )
        card.grid(row=row, column=0, padx=Theme.PAD_LG, pady=Theme.PAD_MD, sticky="ew")
        card.grid_columnconfigure(0, weight=1)
        return card

    def _build_watch_card(self):
        card = self._card(1)

        self._section_label(card, 0, "Watch Directory")
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

        self.monitor_var = ctk.BooleanVar(value=config_service.get("monitor_enabled", True))
        self.monitor_switch = ctk.CTkSwitch(
            card,
            text="Enable Real-time Monitoring",
            variable=self.monitor_var,
            progress_color=Theme.ACCENT,
            text_color=Theme.TEXT_SECONDARY,
        )
        self.monitor_switch.grid(row=2, column=0, padx=Theme.PAD_LG, pady=Theme.PAD_MD, sticky="w")

        self._section_label(card, 3, "Collision Strategy")
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
        self.strategy_option.grid(row=4, column=0, padx=Theme.PAD_LG, pady=(0, Theme.PAD_LG), sticky="w")

    def _build_automation_card(self):
        card = self._card(2)

        self._section_label(card, 0, "Scheduled Scans")
        automation = config_service.get("automation", {})
        self.auto_scan_var = ctk.BooleanVar(value=automation.get("enable_auto_scan", False))
        self.auto_scan_switch = ctk.CTkSwitch(
            card,
            text="Enable Scheduled Scanning",
            variable=self.auto_scan_var,
            progress_color=Theme.ACCENT,
            text_color=Theme.TEXT_SECONDARY,
        )
        self.auto_scan_switch.grid(row=1, column=0, padx=Theme.PAD_LG, pady=Theme.PAD_MD, sticky="w")

        interval_row = ctk.CTkFrame(card, fg_color="transparent")
        interval_row.grid(row=2, column=0, padx=Theme.PAD_LG, pady=(0, Theme.PAD_LG), sticky="w")
        ctk.CTkLabel(
            interval_row,
            text="Scan every",
            text_color=Theme.TEXT_SECONDARY,
            font=ctk.CTkFont(size=Theme.FONT_SMALL_SIZE),
        ).pack(side="left")
        self.interval_entry = ctk.CTkEntry(
            interval_row,
            width=70,
            fg_color=Theme.BG_MAIN,
            border_color=Theme.BORDER,
            text_color=Theme.TEXT_PRIMARY,
            height=Theme.INPUT_H,
        )
        self.interval_entry.insert(0, str(automation.get("auto_scan_interval_min", 60)))
        self.interval_entry.pack(side="left", padx=Theme.PAD_SM)
        ctk.CTkLabel(
            interval_row,
            text="minutes",
            text_color=Theme.TEXT_SECONDARY,
            font=ctk.CTkFont(size=Theme.FONT_SMALL_SIZE),
        ).pack(side="left")

    def _build_logging_card(self):
        card = self._card(3)

        self._section_label(card, 0, "Log Level")
        self.log_level_option = ctk.CTkOptionMenu(
            card,
            values=["DEBUG", "INFO", "WARNING", "ERROR"],
            fg_color=Theme.BG_RAISED,
            button_color=Theme.ACCENT_DARK,
            button_hover_color=Theme.ACCENT,
            text_color=Theme.TEXT_PRIMARY,
            dropdown_fg_color=Theme.BG_ELEVATED,
            dropdown_hover_color=Theme.BG_RAISED,
            dropdown_text_color=Theme.TEXT_PRIMARY,
        )
        self.log_level_option.set(config_service.get("log_level", "INFO"))
        self.log_level_option.grid(row=1, column=0, padx=Theme.PAD_LG, pady=(0, Theme.PAD_LG), sticky="w")

    def _build_cleanup_card(self):
        card = self._card(4)

        self._section_label(card, 0, "Cleanup")
        cleanup = config_service.get("cleanup", {})
        self.dry_run_var = ctk.BooleanVar(value=cleanup.get("dry_run", True))
        self.dry_run_switch = ctk.CTkSwitch(
            card,
            text="Safe Mode (dry-run — preview results, delete nothing)",
            variable=self.dry_run_var,
            progress_color=Theme.SUCCESS,
            text_color=Theme.TEXT_SECONDARY,
        )
        self.dry_run_switch.grid(row=1, column=0, padx=Theme.PAD_LG, pady=Theme.PAD_MD, sticky="w")

        self._section_label(card, 2, "Orphan Files")
        self.orphans_option = ctk.CTkOptionMenu(
            card,
            values=["move_to_misc", "delete", "ignore"],
            fg_color=Theme.BG_RAISED,
            button_color=Theme.ACCENT_DARK,
            button_hover_color=Theme.ACCENT,
            text_color=Theme.TEXT_PRIMARY,
            dropdown_fg_color=Theme.BG_ELEVATED,
            dropdown_hover_color=Theme.BG_RAISED,
            dropdown_text_color=Theme.TEXT_PRIMARY,
        )
        self.orphans_option.set(cleanup.get("handle_orphans", "move_to_misc"))
        self.orphans_option.grid(row=3, column=0, padx=Theme.PAD_LG, pady=(0, Theme.PAD_LG), sticky="w")

    def save_settings(self):
        new_config = config_service.config.copy()
        new_config["watch_directory"] = self.watch_dir_entry.get()
        new_config["monitor_enabled"] = self.monitor_var.get()
        new_config["collision_strategy"] = self.strategy_option.get()

        automation = new_config.get("automation", {}).copy()
        automation["enable_auto_scan"] = self.auto_scan_var.get()
        try:
            automation["auto_scan_interval_min"] = max(1, int(self.interval_entry.get()))
        except ValueError:
            logger.warning("Invalid scan interval; keeping previous value.")
        new_config["automation"] = automation

        new_config["log_level"] = self.log_level_option.get()

        cleanup = new_config.get("cleanup", {}).copy()
        cleanup["dry_run"] = self.dry_run_var.get()
        cleanup["handle_orphans"] = self.orphans_option.get()
        new_config["cleanup"] = cleanup

        config_service.save_config(new_config)
        logger.setLevel(getattr(logging, new_config["log_level"]))
        logger.info("Settings saved via GUI")

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