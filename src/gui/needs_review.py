"""
Needs Review View
-----------------
Human-in-the-loop queue (Step 6.4): files the confidence gate left in
place as ``ask`` or ``hold``. Each row shows why the gate stopped the
file; the user either approves a move into its category folder or
ignores it (which clears the gate state without moving).
"""
import functools
import threading
from pathlib import Path

import customtkinter as ctk

from src.core.organizer import organizer
from src.services.db_service import db_service
from src.services.logger import logger
from .theme import Theme


class NeedsReviewFrame(ctk.CTkFrame):
    """Queue of gated files awaiting a human decision."""
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=Theme.PAD_LG, pady=(24, Theme.PAD_MD), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        self.title_label = ctk.CTkLabel(
            header,
            text="Needs Review",
            text_color=Theme.TEXT_PRIMARY,
            font=ctk.CTkFont(size=Theme.FONT_H2_SIZE, weight="bold"),
        )
        self.title_label.grid(row=0, column=0, sticky="w")

        self.refresh_btn = ctk.CTkButton(
            header,
            text="Refresh",
            command=self.refresh,
            fg_color="transparent",
            border_width=1,
            border_color=Theme.BORDER_LIGHT,
            hover_color=Theme.BG_RAISED,
            text_color=Theme.TEXT_PRIMARY,
            height=Theme.BTN_H,
            corner_radius=Theme.RADIUS_MD,
            font=ctk.CTkFont(size=Theme.FONT_BODY_SIZE),
        )
        self.refresh_btn.grid(row=0, column=1, sticky="e")

        self.summary_label = ctk.CTkLabel(
            self,
            text="",
            text_color=Theme.TEXT_SECONDARY,
            font=ctk.CTkFont(size=Theme.FONT_SMALL_SIZE),
        )
        self.summary_label.grid(row=1, column=0, padx=Theme.PAD_LG, pady=(0, Theme.PAD_MD), sticky="w")

        self.list_container = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
        )
        self.list_container.grid(row=2, column=0, padx=Theme.PAD_LG, pady=Theme.PAD_MD, sticky="nsew")

        self.refresh()

    def queue_count(self) -> int:
        return db_service.count_needs_review()

    def _clear_list(self):
        for child in self.list_container.winfo_children():
            child.destroy()

    def refresh(self):
        """Rebuilds the queue. Stale entries (file already gone) are
        resolved silently so they cannot wedge the queue forever."""
        rows = db_service.query_needs_review()
        self._clear_list()

        still_present = [r for r in rows if Path(r["path"]).exists()]
        stale = [r for r in rows if not Path(r["path"]).exists()]
        for r in stale:
            db_service.resolve_review(Path(r["path"]))

        if not still_present:
            self._show_empty_state(len(rows), len(stale))
            return

        self.summary_label.configure(
            text=f"{len(still_present)} file(s) waiting — auto-moved files are not listed here."
        )
        for row in still_present:
            self._add_row(row)

    def _show_empty_state(self, queued: int, stale: int):
        if queued == 0:
            self.summary_label.configure(text="No files waiting for review. All clear.")
        else:
            self.summary_label.configure(
                text=f"{stale} queued file(s) no longer exist and were removed from the queue."
            )
        ctk.CTkLabel(
            self.list_container,
            text="Nothing to review — every new file was handled automatically.",
            text_color=Theme.TEXT_MUTED,
            font=ctk.CTkFont(size=Theme.FONT_BODY_SIZE),
        ).pack(pady=(Theme.PAD_LG, Theme.PAD_LG))

    def _add_row(self, row: dict):
        path = Path(row["path"])

        card = ctk.CTkFrame(
            self.list_container,
            fg_color=Theme.BG_ELEVATED,
            corner_radius=Theme.RADIUS_MD,
            border_width=1,
            border_color=Theme.BORDER,
        )
        card.pack(fill="x", pady=(0, Theme.PAD_SM))
        card.grid_columnconfigure(0, weight=1)

        is_ask = row["gate_status"] == "ask"
        status_color = Theme.WARNING if is_ask else Theme.ERROR
        status_soft = Theme.WARNING_SOFT if is_ask else Theme.ERROR_SOFT
        cat_color = Theme.category_color(row["category"])

        # Row 0: status chip + filename + category chip
        row0 = ctk.CTkFrame(card, fg_color="transparent")
        row0.grid(row=0, column=0, padx=Theme.PAD_MD, pady=(Theme.PAD_MD, 0), sticky="ew")

        status_chip = ctk.CTkLabel(
            row0,
            text=row["gate_status"].upper(),
            text_color=status_color,
            fg_color=status_soft,
            corner_radius=Theme.RADIUS_SM,
            font=ctk.CTkFont(size=Theme.FONT_SMALL_SIZE, weight="bold"),
        )
        status_chip.grid(row=0, column=0, padx=(0, Theme.PAD_SM), sticky="w")

        ctk.CTkLabel(
            row0,
            text=path.name,
            text_color=Theme.TEXT_PRIMARY,
            font=ctk.CTkFont(size=Theme.FONT_BODY_SIZE, weight="bold"),
        ).grid(row=0, column=1, padx=(0, Theme.PAD_SM), sticky="w")

        cat_chip = ctk.CTkLabel(
            row0,
            text=row["category"],
            text_color=cat_color,
            font=ctk.CTkFont(size=Theme.FONT_SMALL_SIZE),
        )
        cat_chip.grid(row=0, column=2, sticky="w")
        row0.grid_columnconfigure(1, weight=1)

        # Row 1: metadata + confidence
        meta = f"{row['size'] / 1024:.1f} KB  ·  confidence {row['gate_confidence']:.2f}"
        ctk.CTkLabel(
            card,
            text=meta,
            text_color=Theme.TEXT_SECONDARY,
            font=ctk.CTkFont(size=Theme.FONT_SMALL_SIZE),
        ).grid(row=1, column=0, padx=Theme.PAD_MD, pady=(Theme.PAD_SM, 0), sticky="w")

        # Row 2: gate reason in mono
        ctk.CTkLabel(
            card,
            text=row["gate_reason"] or "gated for review",
            text_color=Theme.TEXT_SECONDARY,
            font=ctk.CTkFont(family=Theme.FONT_MONO, size=Theme.FONT_SMALL_SIZE),
        ).grid(row=2, column=0, padx=Theme.PAD_MD, pady=(Theme.PAD_SM, Theme.PAD_SM), sticky="w")

        # Row 3: actions
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.grid(row=3, column=0, padx=Theme.PAD_MD, pady=(0, Theme.PAD_MD), sticky="ew")

        ctk.CTkButton(
            actions,
            text="Approve & Move",
            command=functools.partial(self._approve_move, path, row["category"]),
            fg_color=Theme.ACCENT,
            hover_color=Theme.ACCENT_HOVER,
            text_color="#ffffff",
            height=Theme.BTN_H,
            corner_radius=Theme.RADIUS_MD,
            font=ctk.CTkFont(size=Theme.FONT_BODY_SIZE),
        ).grid(row=0, column=0, padx=(0, Theme.PAD_SM))

        ctk.CTkButton(
            actions,
            text="Ignore",
            command=functools.partial(self._ignore, path),
            fg_color="transparent",
            border_width=1,
            border_color=Theme.BORDER_LIGHT,
            hover_color=Theme.BG_RAISED,
            text_color=Theme.TEXT_SECONDARY,
            height=Theme.BTN_H,
            corner_radius=Theme.RADIUS_MD,
            font=ctk.CTkFont(size=Theme.FONT_BODY_SIZE),
        ).grid(row=0, column=1)

    def _approve_move(self, path: Path, category: str):
        thread = threading.Thread(
            target=self._approve_move_worker, args=(path, category), daemon=True
        )
        thread.start()

    def _approve_move_worker(self, path: Path, category: str):
        try:
            target_dir = path.parent / category
            final = organizer.move_file(path, target_dir)
            if final is None:
                logger.warning(f"Approve-move failed for {path}")
                self.after(0, self.refresh)
                return
            db_service.remove_file(path)
            db_service.upsert_file(final)
            logger.info(f"Approved move: {path} -> {final}")
        except Exception as e:
            logger.error(f"Approve-move error for {path}: {e}", exc_info=True)
        finally:
            self.after(0, self.refresh)

    def _ignore(self, path: Path):
        db_service.resolve_review(path)
        logger.info(f"Gated file ignored (kept in place): {path}")
        self.refresh()