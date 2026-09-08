"""
Maintenance View
----------------
Interface for performing manual directory health audits and cleanup operations.
Displays detailed reports on duplicates, orphans, and space savings.
"""
import customtkinter as ctk
import threading
from src.services.health_service import health_service
from src.services.config_service import config_service
from src.services.logger import logger
from tkinter import messagebox
from .theme import Theme

class MaintenanceFrame(ctk.CTkFrame):
    """GUI component for orchestrating file system health and cleanup tasks."""
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        self.grid_columnconfigure(0, weight=1)
        
        # Title
        ctk.CTkLabel(
            self,
            text="System Maintenance & Health",
            text_color=Theme.TEXT_PRIMARY,
            font=ctk.CTkFont(size=Theme.FONT_H2_SIZE, weight="bold"),
        ).grid(row=0, column=0, padx=Theme.PAD_LG, pady=(24, Theme.PAD_LG), sticky="w")
        
        # Actions
        self.action_frame = ctk.CTkFrame(
            self,
            fg_color=Theme.BG_ELEVATED,
            corner_radius=Theme.RADIUS_LG,
            border_width=1,
            border_color=Theme.BORDER,
        )
        self.action_frame.grid(row=1, column=0, padx=Theme.PAD_LG, pady=Theme.PAD_MD, sticky="ew")
        
        self.audit_btn = ctk.CTkButton(
            self.action_frame,
            text="Run Health Audit",
            command=self.run_audit_threaded,
            fg_color="transparent",
            border_width=1,
            border_color=Theme.BORDER_LIGHT,
            hover_color=Theme.BG_RAISED,
            text_color=Theme.TEXT_PRIMARY,
            height=Theme.BTN_H,
            corner_radius=Theme.RADIUS_MD,
            font=ctk.CTkFont(size=Theme.FONT_BODY_SIZE),
        )
        self.audit_btn.grid(row=0, column=0, padx=Theme.PAD_LG, pady=Theme.PAD_LG)
        
        self.cleanup_btn = ctk.CTkButton(
            self.action_frame,
            text="Execute Cleanup",
            command=self.confirm_cleanup,
            fg_color="transparent",
            border_width=1,
            border_color=Theme.ERROR,
            hover_color=Theme.ERROR_WASH,
            text_color=Theme.ERROR,
            height=Theme.BTN_H,
            corner_radius=Theme.RADIUS_MD,
            font=ctk.CTkFont(size=Theme.FONT_BODY_SIZE),
        )
        self.cleanup_btn.grid(row=0, column=1, padx=Theme.PAD_LG, pady=Theme.PAD_LG)
        self.cleanup_btn.configure(state="disabled")

        # Report Area
        self.report_label = ctk.CTkLabel(
            self,
            text="No audit performed yet.",
            text_color=Theme.TEXT_SECONDARY,
            font=ctk.CTkFont(size=Theme.FONT_BODY_SIZE),
        )
        self.report_label.grid(row=2, column=0, padx=Theme.PAD_LG, pady=Theme.PAD_MD, sticky="w")
        
        self.report_box = ctk.CTkTextbox(
            self,
            height=200,
            state="disabled",
            fg_color=Theme.BG_DEEP,
            text_color=Theme.TEXT_SECONDARY,
            border_width=1,
            border_color=Theme.BORDER,
            corner_radius=Theme.RADIUS_MD,
            font=ctk.CTkFont(family=Theme.FONT_MONO, size=Theme.FONT_SMALL_SIZE),
        )
        self.report_box.grid(row=3, column=0, padx=Theme.PAD_LG, pady=Theme.PAD_MD, sticky="nsew")
        
        self.progress_bar = ctk.CTkProgressBar(
            self,
            progress_color=Theme.ACCENT,
            fg_color=Theme.BG_RAISED,
        )
        self.progress_bar.grid(row=4, column=0, padx=Theme.PAD_LG, pady=Theme.PAD_MD, sticky="ew")
        self.progress_bar.set(0)

        self.last_report = None

    def run_audit_threaded(self):
        self.audit_btn.configure(state="disabled")
        self.report_label.configure(text="Scanning directory...")
        self.progress_bar.start()
        
        thread = threading.Thread(target=self._run_audit)
        thread.start()

    def _run_audit(self):
        try:
            report = health_service.run_audit()
            self.last_report = report
            self.after(0, lambda: self.show_report(report))
        except Exception as e:
            logger.error(f"Audit failed: {e}")
            self.after(0, lambda: self.report_label.configure(text="Audit failed. Check logs."))
        finally:
            self.after(0, self.progress_bar.stop)
            self.after(0, lambda: self.audit_btn.configure(state="normal"))

    def show_report(self, report):
        self.report_label.configure(text="Audit Summary:")
        
        summary = (
            f"Empty Folders: {len(report['empty_folders'])}\n"
            f"Duplicates: {len(report['duplicates'])}\n"
            f"Orphans: {len(report['orphans'])}\n"
            f"0-Byte Files: {len(report['zero_byte_files'])}\n"
            f"Potential Space Reclaimed: {report['space_waste_bytes'] / 1024 / 1024:.2f} MB"
        )
        
        self.report_box.configure(state="normal")
        self.report_box.delete("1.0", "end")
        self.report_box.insert("1.0", summary)
        self.report_box.configure(state="disabled")
        
        self.cleanup_btn.configure(state="normal")

    def confirm_cleanup(self):
        dry_run = config_service.get("cleanup", {}).get("dry_run", True)
        msg = "Ready to perform cleanup?"
        if not dry_run:
            msg += "\n\nWARNING: DRY-RUN is OFF. This will actually DELETE or MOVE files permanently."
        
        if messagebox.askyesno("Confirm Cleanup", msg):
            stats = health_service.execute_cleanup(self.last_report)
            messagebox.showinfo("Cleanup Result", f"Deleted: {stats['deleted']}\nMoved: {stats['moved']}\nSaved: {stats['saved_bytes']/1024:.2f} KB")
            self.cleanup_btn.configure(state="disabled")
