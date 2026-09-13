"""
Dashboard View
--------------
Primary status overview: system health, real-time monitor status, and live
index statistics. Stat cards and the category panel are driven by real data
(``get_stats`` / ``count_needs_review``), styled with the deep blue-violet
palette from ``prototype/design.html``.
"""
import customtkinter as ctk
from src.services.observer import observer_service
from src.services.config_service import config_service
from src.services.db_service import db_service
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
            text="System Overview",
            text_color=Theme.TEXT_PRIMARY,
            font=ctk.CTkFont(size=Theme.FONT_H1_SIZE, weight="bold"),
        ).grid(row=0, column=0, padx=Theme.PAD_LG, pady=(24, Theme.PAD_LG), sticky="w")

        # Status card (dot + text + primary CTA, hairline border)
        self.status_frame = ctk.CTkFrame(
            self,
            fg_color=Theme.BG_ELEVATED,
            corner_radius=Theme.RADIUS_LG,
            border_width=1,
            border_color=Theme.BORDER,
        )
        self.status_frame.grid(row=1, column=0, padx=Theme.PAD_LG, pady=Theme.PAD_MD, sticky="ew")
        self.status_frame.grid_columnconfigure(1, weight=1)

        self.status_dot = ctk.CTkLabel(
            self.status_frame,
            text="●",
            text_color=Theme.NEUTRAL,
            font=ctk.CTkFont(size=Theme.FONT_BODY_SIZE),
        )
        self.status_dot.grid(row=0, column=0, padx=(Theme.PAD_LG, Theme.PAD_SM), pady=Theme.PAD_MD)

        self.status_label = ctk.CTkLabel(
            self.status_frame,
            text="Status: INACTIVE",
            text_color=Theme.TEXT_PRIMARY,
            font=ctk.CTkFont(size=Theme.FONT_BODY_SIZE),
        )
        self.status_label.grid(row=0, column=1, padx=(0, Theme.PAD_LG), pady=Theme.PAD_MD, sticky="w")

        self.start_btn = ctk.CTkButton(
            self.status_frame,
            text="Start Monitor",
            command=self.toggle_monitor,
            fg_color=Theme.ACCENT,
            hover_color=Theme.ACCENT_HOVER,
            height=Theme.BTN_H,
            corner_radius=Theme.RADIUS_MD,
            font=ctk.CTkFont(size=Theme.FONT_BODY_SIZE),
        )
        self.start_btn.grid(row=0, column=2, padx=(0, Theme.PAD_LG), pady=Theme.PAD_MD)

        # Stat cards row (real data, refreshed on the same tick as status)
        self.stats_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.stats_frame.grid(row=2, column=0, padx=Theme.PAD_LG, pady=Theme.PAD_MD, sticky="ew")
        for col in range(3):
            self.stats_frame.grid_columnconfigure(col, weight=1, uniform="stats")

        self.indexed_value = ctk.CTkLabel(self.stats_frame, text="–", text_color=Theme.TEXT_PRIMARY,
                                          font=ctk.CTkFont(size=Theme.FONT_H2_SIZE, weight="bold"))
        self.indexed_value.grid(row=0, column=0, padx=(0, Theme.PAD_MD), pady=(0, 0), sticky="w")

        self.review_value = ctk.CTkLabel(self.stats_frame, text="–", text_color=Theme.WARNING,
                                         font=ctk.CTkFont(size=Theme.FONT_H2_SIZE, weight="bold"))
        self.review_value.grid(row=0, column=1, padx=(0, Theme.PAD_MD), pady=(0, 0), sticky="w")

        self.categories_value = ctk.CTkLabel(self.stats_frame, text="–", text_color=Theme.INFO,
                                             font=ctk.CTkFont(size=Theme.FONT_H2_SIZE, weight="bold"))
        self.categories_value.grid(row=0, column=2, padx=(0, 0), pady=(0, 0), sticky="w")

        ctk.CTkLabel(self.stats_frame, text="Files Indexed", text_color=Theme.TEXT_MUTED,
                     font=ctk.CTkFont(size=Theme.FONT_SMALL_SIZE)).grid(
            row=1, column=0, padx=(0, Theme.PAD_MD), sticky="w")
        ctk.CTkLabel(self.stats_frame, text="Needs Review", text_color=Theme.TEXT_MUTED,
                     font=ctk.CTkFont(size=Theme.FONT_SMALL_SIZE)).grid(
            row=1, column=1, padx=(0, Theme.PAD_MD), sticky="w")
        ctk.CTkLabel(self.stats_frame, text="Categories", text_color=Theme.TEXT_MUTED,
                     font=ctk.CTkFont(size=Theme.FONT_SMALL_SIZE)).grid(
            row=1, column=2, sticky="w")

        # Files by Category panel (colored bars per real distribution)
        self.cat_panel = ctk.CTkFrame(
            self,
            fg_color=Theme.BG_ELEVATED,
            corner_radius=Theme.RADIUS_LG,
            border_width=1,
            border_color=Theme.BORDER,
        )
        self.cat_panel.grid(row=3, column=0, padx=Theme.PAD_LG, pady=Theme.PAD_MD, sticky="nsew")
        self.cat_panel.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        self.cat_bars = None  # rebuilt lazily on each stats refresh

        # Footer: watch path + settings
        self.info_label = ctk.CTkLabel(
            self,
            text=f"Watching: {config_service.get('watch_directory')}",
            text_color=Theme.TEXT_MUTED,
            font=ctk.CTkFont(size=Theme.FONT_SMALL_SIZE, slant="italic"),
        )
        self.info_label.grid(row=4, column=0, padx=Theme.PAD_LG, pady=Theme.PAD_SM, sticky="w")

        self.settings_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.settings_frame.grid(row=5, column=0, padx=Theme.PAD_LG, pady=Theme.PAD_MD, sticky="w")

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

        # Persist preference - merge into a copy of the full config.
        # save_config() replaces the whole file, so passing only
        # {"automation": auto} would wipe categories/cleanup/watch settings.
        config = config_service.config.copy()
        auto = config.get("automation", {}).copy()
        auto["run_on_startup"] = self.startup_var.get()
        config["automation"] = auto
        config_service.save_config(config)

    def toggle_monitor(self):
        if observer_service.is_running:
            observer_service.stop()
            logger.info("Monitor stopped manually via dashboard.")
        else:
            observer_service.start()
            logger.info("Monitor started manually via dashboard.")
        self.update_status()

    def _refresh_stats(self):
        """Rebuilds stat values + category bars from live DB data."""
        stats = db_service.get_stats()
        if not stats or "error" in stats:
            return
        total = stats.get("total_files", 0)
        categories = stats.get("categories", {})
        self.indexed_value.configure(text=f"{total:,}")
        self.review_value.configure(text=str(db_service.count_needs_review()))
        self.categories_value.configure(text=str(len(categories)))

        if self.cat_bars is not None:
            for child in self.cat_bars.winfo_children():
                child.destroy()
        else:
            ctk.CTkLabel(
                self.cat_panel,
                text="Files by Category",
                text_color=Theme.TEXT_PRIMARY,
                font=ctk.CTkFont(size=Theme.FONT_H2_SIZE, weight="bold"),
            ).grid(row=0, column=0, padx=Theme.PAD_LG, pady=(Theme.PAD_MD, Theme.PAD_SM), sticky="w")
            self.cat_bars = ctk.CTkFrame(self.cat_panel, fg_color="transparent")
            self.cat_bars.grid(row=1, column=0, padx=Theme.PAD_LG, pady=(0, Theme.PAD_LG), sticky="ew")

        if not categories:
            ctk.CTkLabel(
                self.cat_bars,
                text="No files indexed yet.",
                text_color=Theme.TEXT_MUTED,
                font=ctk.CTkFont(size=Theme.FONT_BODY_SIZE),
            ).pack(anchor="w")
            return

        max_count = max(categories.values())
        for row, (name, count) in enumerate(sorted(categories.items(), key=lambda kv: -kv[1])):
            color = Theme.category_color(name)
            bar_row = ctk.CTkFrame(self.cat_bars, fg_color="transparent")
            bar_row.pack(fill="x", pady=(2, 2))
            bar_row.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(
                bar_row,
                text=name,
                text_color=Theme.TEXT_SECONDARY,
                font=ctk.CTkFont(size=Theme.FONT_SMALL_SIZE),
            ).grid(row=0, column=0, padx=(0, Theme.PAD_MD), sticky="w")

            bar_bg = ctk.CTkFrame(bar_row, fg_color=Theme.BG_INSET, corner_radius=Theme.RADIUS_SM,
                                  height=8)
            bar_bg.grid(row=0, column=1, sticky="ew")
            bar_bg.grid_propagate(False)
            bar_bg.grid_columnconfigure(0, weight=1)

            fill = ctk.CTkFrame(bar_bg, fg_color=color, corner_radius=Theme.RADIUS_SM, height=8)
            fill.grid(row=0, column=0, sticky="w")
            fill.grid_propagate(False)
            frac = count / max_count if max_count else 0
            fill.configure(width=max(8, int(bar_bg.winfo_width() * frac) or 8))

            ctk.CTkLabel(
                bar_row,
                text=f"{count:,}",
                text_color=Theme.TEXT_MUTED,
                font=ctk.CTkFont(size=Theme.FONT_SMALL_SIZE),
            ).grid(row=0, column=2, padx=(Theme.PAD_MD, 0), sticky="e")

            # width follows the real fraction once the frame is mapped
            self._schedule_bar_width(fill, bar_bg, frac)

    def _schedule_bar_width(self, fill, bar_bg, frac: float):
        def _size():
            try:
                fill.configure(width=max(8, int(bar_bg.winfo_width() * frac) or 8))
            except Exception:
                pass
        self.after(100, _size)

    def update_status(self):
        if observer_service.is_running:
            self.status_dot.configure(text_color=Theme.SUCCESS)
            self.status_label.configure(text="Status: ACTIVE", text_color=Theme.SUCCESS)
            self.start_btn.configure(text="Stop Monitor")
        else:
            self.status_dot.configure(text_color=Theme.NEUTRAL)
            self.status_label.configure(text="Status: INACTIVE", text_color=Theme.TEXT_PRIMARY)
            self.start_btn.configure(text="Start Monitor", fg_color=Theme.ACCENT, hover_color=Theme.ACCENT_HOVER)

        self.info_label.configure(text=f"Watching: {config_service.get('watch_directory')}")
        self._refresh_stats()
        self.after(2000, self.update_status)