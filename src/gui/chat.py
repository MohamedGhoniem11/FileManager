"""
Chat Interface
--------------
Interactive chat panel for the Intelligent Assistant.
Supports message history, interactive search results, and config confirmation.
"""
import customtkinter as ctk
import threading
from src.services.nlp_service import get_nlp_service
from src.services.db_service import db_service
from src.core.config_agent import config_agent
from src.services.logger import logger
from .theme import Theme

class ChatFrame(ctk.CTkFrame):
    """The Assistant's conversation interface."""
    
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # Header
        ctk.CTkLabel(
            self,
            text="AI Assistant",
            text_color=Theme.TEXT_PRIMARY,
            font=ctk.CTkFont(size=Theme.FONT_H1_SIZE, weight="bold"),
        ).grid(row=0, column=0, padx=Theme.PAD_LG, pady=(24, Theme.PAD_LG), sticky="w")
        
        # Chat History
        self.history_box = ctk.CTkTextbox(
            self,
            state="disabled",
            wrap="word",
            fg_color=Theme.BG_DEEP,
            text_color=Theme.TEXT_SECONDARY,
            border_width=1,
            border_color=Theme.BORDER,
            corner_radius=Theme.RADIUS_MD,
        )
        self.history_box.grid(row=1, column=0, padx=Theme.PAD_LG, pady=Theme.PAD_MD, sticky="nsew")
        
        # Input Area
        self.input_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.input_frame.grid(row=2, column=0, padx=Theme.PAD_LG, pady=Theme.PAD_LG, sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=1)
        
        self.user_input = ctk.CTkEntry(
            self.input_frame,
            placeholder_text="Ask me: 'find my pdfs' or 'stop organizing zip files'...",
            fg_color=Theme.BG_MAIN,
            border_color=Theme.BORDER,
            text_color=Theme.TEXT_PRIMARY,
            placeholder_text_color=Theme.TEXT_MUTED,
            height=Theme.INPUT_H,
        )
        self.user_input.grid(row=0, column=0, padx=(0, Theme.PAD_MD), sticky="ew")
        self.user_input.bind("<Return>", lambda e: self.send_message())
        
        self.send_btn = ctk.CTkButton(
            self.input_frame,
            text="Send",
            width=90,
            command=self.send_message,
            fg_color=Theme.ACCENT,
            hover_color=Theme.ACCENT_HOVER,
            height=Theme.INPUT_H,
            corner_radius=Theme.RADIUS_MD,
            font=ctk.CTkFont(size=Theme.FONT_BODY_SIZE),
        )
        self.send_btn.grid(row=0, column=1)
        
        # Example Prompts Panel
        self._create_example_panel()
        
        # Confirmation Area (Hidden by default)
        self.confirm_frame = ctk.CTkFrame(
            self,
            fg_color=Theme.BG_ELEVATED,
            corner_radius=Theme.RADIUS_MD,
            border_width=1,
            border_color=Theme.BORDER,
        )
        self.confirm_label = ctk.CTkLabel(
            self.confirm_frame,
            text="Proposed Change:",
            text_color=Theme.TEXT_PRIMARY,
            font=ctk.CTkFont(size=Theme.FONT_SMALL_SIZE),
        )
        self.confirm_label.pack(side="left", padx=Theme.PAD_LG, pady=Theme.PAD_SM)
        self.yes_btn = ctk.CTkButton(
            self.confirm_frame,
            text="Yes",
            width=60,
            height=Theme.INPUT_H,
            fg_color=Theme.ACCENT,
            hover_color=Theme.ACCENT_HOVER,
            command=self.apply_proposed_change,
        )
        self.yes_btn.pack(side="left", padx=Theme.PAD_SM)
        self.no_btn = ctk.CTkButton(
            self.confirm_frame,
            text="No",
            width=60,
            height=Theme.INPUT_H,
            fg_color="transparent",
            border_width=1,
            border_color=Theme.BORDER_LIGHT,
            hover_color=Theme.BG_RAISED,
            text_color=Theme.TEXT_PRIMARY,
            command=self.cancel_proposed_change,
        )
        self.no_btn.pack(side="left", padx=Theme.PAD_SM)
        
        self.proposed_patch = None
        
        # Check if first run for tutorial
        self.after(500, self._check_first_run)

    def _create_example_panel(self):
        """Creates a scrollable or grid panel of clickable examples."""
        self.example_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.example_frame.grid(row=4, column=0, padx=Theme.PAD_LG, pady=(0, Theme.PAD_LG), sticky="ew")
        
        ctk.CTkLabel(
            self.example_frame,
            text="Try these:",
            text_color=Theme.TEXT_MUTED,
            font=ctk.CTkFont(size=Theme.FONT_SMALL_SIZE, weight="bold"),
        ).pack(side="left", padx=(0, Theme.PAD_MD))
        
        examples = [
            ("Find PDFs", "find my pdfs"),
            ("Scan Downloads", "scan C:/Users/ghoni/Downloads"),
            ("Status", "status"),
            ("Stop ZIPs", "stop organizing zip files"),
            ("Run Cleanup", "run cleanup")
        ]
        
        for label, cmd in examples:
            btn = ctk.CTkButton(
                self.example_frame, 
                text=label, 
                width=80, 
                height=28, 
                font=ctk.CTkFont(size=Theme.FONT_SMALL_SIZE - 1),
                fg_color=Theme.BG_RAISED,
                hover_color=Theme.BORDER_LIGHT,
                text_color=Theme.TEXT_SECONDARY,
                corner_radius=Theme.RADIUS_PILL,
                command=lambda c=cmd: self._fill_and_send(c)
            )
            btn.pack(side="left", padx=Theme.PAD_SM)

    def _fill_and_send(self, cmd: str):
        self.user_input.delete(0, "end")
        self.user_input.insert(0, cmd)
        self.send_message()

    def _check_first_run(self):
        """Shows a welcome tutorial if the user hasn't seen it."""
        # Simple placeholder for first-run logic
        self.add_message("Bot", "🚀 PRO-TIP: You can search by date ('from yesterday') or size ('larger than 50MB')!")

    def add_message(self, sender: str, msg: str):
        self.history_box.configure(state="normal")
        self.history_box.insert("end", f"[{sender}]: {msg}\n\n")
        self.history_box.see("end")
        self.history_box.configure(state="disabled")

    def send_message(self):
        text = self.user_input.get()
        if not text:
            return
            
        self.add_message("You", text)
        self.user_input.delete(0, "end")
        
        # Process in thread to keep GUI responsive
        threading.Thread(target=self._process_request, args=(text,), daemon=True).start()

    def _process_request(self, text: str):
        result = get_nlp_service().parse(text)
        intent = result["intent"]
        entities = result["entities"]
        
        if intent == "search_files":
            files = db_service.query_files(entities)
            if not files:
                self.after(0, lambda: self.add_message("Bot", "I couldn't find any files matching that description."))
            else:
                resp = f"I found {len(files)} files:\n"
                for i, f in enumerate(files[:10]):
                    resp += f"  • {f['filename']} ({f['category']})\n"
                if len(files) > 10:
                    resp += f"  ... and {len(files)-10} more."
                self.after(0, lambda: self.add_message("Bot", resp))
                
        elif intent == "update_config":
            valid, desc, patch = config_agent.validate_and_propose(entities)
            if valid:
                self.proposed_patch = patch
                self.after(0, lambda: self.show_confirmation(desc))
            else:
                self.after(0, lambda: self.add_message("Bot", f"Sorry, I can't do that: {desc}"))
                
        elif intent == "run_cleanup":
            from src.services.config_service import config_service
            if config_service.get("cleanup", {}).get("dry_run", True):
                self.proposed_patch = None
                self.proposed_action_callback = self._run_forced_cleanup
                self.after(0, lambda: self.show_confirmation("⚠️ Safe Mode is ON. Run REAL cleanup?"))
            else:
                self._run_forced_cleanup()



        elif intent == "debug_info" or intent == "show_stats":
             stats = db_service.get_stats()
             if "error" in stats:
                 msg = f"Error accessing DB: {stats['error']}"
             else:
                 msg = f"🔍 **System Status**\n• Total Indexed Files: {stats['total_files']}\n• DB Path: {stats['db_path']}\n\n**Categories:**\n"
                 for cat, count in stats['categories'].items():
                     msg += f"• {cat}: {count}\n"
             self.after(0, lambda: self.add_message("Bot", msg))
             
        elif intent == "unknown":
            self.after(0, lambda: self.add_message("Bot", "I'm not sure what you mean. Try 'scan <path>', 'find pdfs', or 'run cleanup'."))

        elif intent == "scan_path":
            path_str = entities.get("path")
            if not path_str:
                # Default to current watch directory if no path provided
                from src.services.config_service import config_service
                path_str = config_service.get("watch_directory")
                
            self.after(0, lambda: self.add_message("Bot", f"Starting manual scan of: {path_str}..."))
            
            from pathlib import Path
            from src.services.health_service import health_service
            
            # Run scan in thread
            def run_scan():
                result = health_service.scan_and_index(Path(path_str))
                if "error" in result:
                     self.after(0, lambda: self.add_message("Bot", f"❌ Scan failed: {result['error']}"))
                else:
                     self.after(0, lambda: self.add_message("Bot", f"✅ Scan complete!\n• Indexed: {result['indexed']}\n• Errors: {result['errors']}"))
                     
            threading.Thread(target=run_scan, daemon=True).start()

    def show_confirmation(self, desc: str):
        self.confirm_label.configure(text=desc)
        self.confirm_frame.grid(row=3, column=0, padx=20, pady=(0, 20), sticky="ew")

    def _run_forced_cleanup(self):
        self.after(0, lambda: self.add_message("Bot", "Maintenance audit triggered. Please check the Maintenance tab for results."))
        
        # Safest is to update config to False (as user confirmed they want real cleanup).
        from src.services.config_service import config_service
        
        # CRITICAL FIX: Get entire config, modify it, then save back.
        # Previously we were overwriting the whole config with just the cleanup dict.
        current_config = config_service.config.copy()
        if "cleanup" not in current_config:
            current_config["cleanup"] = {}
            
        current_config["cleanup"]["dry_run"] = False
        config_service.save_config(current_config)
        
        from src.services.health_service import health_service
        health_service.run_audit()

    def apply_proposed_change(self):
        if self.proposed_patch:
            config_agent.apply_patch(self.proposed_patch)
            self.add_message("Bot", "Settings updated successfully.")
        
        if hasattr(self, 'proposed_action_callback') and self.proposed_action_callback:
            self.proposed_action_callback()
            
        self.cancel_proposed_change()

    def cancel_proposed_change(self):
        self.confirm_frame.grid_forget()
        self.proposed_patch = None
        self.proposed_action_callback = None
