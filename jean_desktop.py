import threading
import re
import os
import sys
import sqlite3
import subprocess
import glob
import time
import uuid
import customtkinter as ctk
from tkinter import messagebox, filedialog
import ollama
import speech_recognition as sr
import pyttsx3
from PIL import Image, ImageDraw
from duckduckgo_search import DDGS
import keyboard  # Global hotkey listener

# Optional imports for document generation
try:
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

try:
    from pptx import Presentation
    from pptx.util import Inches, Pt
    PPTX_AVAILABLE = True
except ImportError:
    PPTX_AVAILABLE = False

OLLAMA_MODEL = "llama3.2"
DEFAULT_OUTPUT_DIRECTORY = r"C:\Users\joelm\Documents\bee and bce"

# Robust Absolute Pathing for Executable & Script execution
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_FILE = os.path.join(BASE_DIR, "jean_memory.db")

class JeanDesktopApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("AI Assistant")
        self.geometry("1250x780")
        
        # Set programmatic white bold ring window icon
        self.set_dynamic_ring_icon()

        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("dark-blue")

        self.attached_file_content = ""
        self.is_muted = False
        self.is_speaking = False
        self.tts_engine = None  # Reference to active text-to-speech engine
        
        # Active Background Listening Variables
        self.is_active_listening = False
        self.active_listener_thread = None

        # Session Management
        self.current_session_id = None

        # Initialize Database and Load User/Agent Config & Memory
        self.init_db()
        self.load_settings()
        self.init_current_session()

        if not os.path.exists(DEFAULT_OUTPUT_DIRECTORY):
            try:
                os.makedirs(DEFAULT_OUTPUT_DIRECTORY, exist_ok=True)
            except Exception:
                pass

        # Main Layout: 2 Columns (Sidebar left, Chat Window right)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0, minsize=300)  # Sidebar
        self.grid_columnconfigure(1, weight=1)  # Chat Area

        # ---------------- LEFT SIDEBAR ----------------
        self.sidebar = ctk.CTkFrame(self, fg_color="#171717", corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(2, weight=1)
        self.sidebar.grid_columnconfigure(0, weight=1)

        # Header with Dynamic Agent Name & Settings Button
        self.header_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, padx=15, pady=(20, 5), sticky="ew")
        self.header_frame.grid_columnconfigure(0, weight=1)

        self.sidebar_brand = ctk.CTkLabel(
            self.header_frame, text=f"✦ {self.agent_name} Workspace", font=("Segoe UI", 15, "bold"), text_color="#ffffff"
        )
        self.sidebar_brand.grid(row=0, column=0, sticky="w")

        self.settings_btn = ctk.CTkButton(
            self.header_frame, text="⚙️", width=30, height=30, font=("Segoe UI", 12),
            fg_color="transparent", hover_color="#333333", text_color="#cccccc",
            command=self.open_settings_dialog
        )
        self.settings_btn.grid(row=0, column=1, sticky="e")

        # New Chat Button
        self.sidebar_new_chat = ctk.CTkButton(
            self.sidebar, text="+ New Chat", command=self.start_new_chat,
            fg_color="#2f2f2f", hover_color="#3a3a3a", text_color="#ffffff",
            font=("Segoe UI", 13), height=36, corner_radius=8
        )
        self.sidebar_new_chat.grid(row=1, column=0, padx=15, pady=10, sticky="ew")

        # Tabview for History Sessions, Summary, & Agent Memory
        self.sidebar_tabview = ctk.CTkTabview(self.sidebar, fg_color="#1f1f1f", segmented_button_fg_color="#121212", segmented_button_selected_color="#333333")
        self.sidebar_tabview.grid(row=2, column=0, padx=12, pady=10, sticky="nsew")
        
        self.tab_history = self.sidebar_tabview.add("Chats")
        self.tab_summary = self.sidebar_tabview.add("My Summary")
        self.tab_memory = self.sidebar_tabview.add("Agent Memory")

        # Containers inside tabs
        self.history_frame = ctk.CTkScrollableFrame(self.tab_history, fg_color="transparent")
        self.history_frame.pack(fill="both", expand=True)

        self.summary_frame = ctk.CTkScrollableFrame(self.tab_summary, fg_color="transparent")
        self.summary_frame.pack(fill="both", expand=True)
        self.populate_user_summary()

        self.memory_frame = ctk.CTkScrollableFrame(self.tab_memory, fg_color="transparent")
        self.memory_frame.pack(fill="both", expand=True)
        self.populate_agent_memory()

        # ---------------- RIGHT MAIN CHAT AREA ----------------
        self.right_container = ctk.CTkFrame(self, fg_color="#212121", corner_radius=0)
        self.right_container.grid(row=0, column=1, sticky="nsew")
        self.right_container.grid_rowconfigure(0, weight=1)
        self.right_container.grid_rowconfigure(1, weight=0)
        self.right_container.grid_columnconfigure(0, weight=1)

        # Top Control Bar
        self.top_bar = ctk.CTkFrame(self.right_container, fg_color="#171717", height=50, corner_radius=0)
        self.top_bar.grid(row=0, column=0, sticky="new", padx=0, pady=0)
        self.top_bar.grid_columnconfigure(0, weight=1)

        self.copy_all_button = ctk.CTkButton(
            self.top_bar, text="Copy Chat", command=self.copy_full_chat, 
            fg_color="transparent", hover_color="#2f2f2f", text_color="#ececec", 
            font=("Segoe UI", 12), width=85, height=32, corner_radius=6
        )
        self.copy_all_button.pack(side="right", padx=10, pady=9)

        self.mute_button = ctk.CTkButton(
            self.top_bar, text="🔊 Voice", command=self.toggle_mute, 
            fg_color="transparent", hover_color="#2f2f2f", text_color="#ececec", 
            font=("Segoe UI", 12), width=75, height=32, corner_radius=6
        )
        self.mute_button.pack(side="right", padx=2, pady=9)

        # Active Listening Switch Option
        self.listen_switch = ctk.CTkSwitch(
            self.top_bar, text="🎙️ Active Listen", command=self.toggle_active_listening,
            font=("Segoe UI", 12), text_color="#cccccc", progress_color="#00e5ff"
        )
        self.listen_switch.pack(side="right", padx=15, pady=9)

        # Chat Scrollable Frame
        self.chat_container = ctk.CTkScrollableFrame(self.right_container, fg_color="#212121", corner_radius=0)
        self.chat_container.grid(row=0, column=0, sticky="nsew", padx=0, pady=(50, 80))
        self.chat_container.grid_columnconfigure(0, weight=1)

        # Input Capsule Area
        self.input_wrapper = ctk.CTkFrame(self.right_container, fg_color="#212121", height=80, corner_radius=0)
        self.input_wrapper.grid(row=1, column=0, sticky="sew", padx=0, pady=0)
        self.input_wrapper.grid_columnconfigure(0, weight=1)

        self.input_pill = ctk.CTkFrame(self.input_wrapper, fg_color="#2f2f2f", corner_radius=24, height=54)
        self.input_pill.pack(fill="x", padx=30, pady=12)
        self.input_pill.grid_columnconfigure(0, weight=1)

        self.user_input = ctk.CTkEntry(
            self.input_pill, 
            placeholder_text=f"Message {self.agent_name}, type 'open [app]', or press Ctrl+Space...", 
            font=("Segoe UI", 14), 
            height=40,
            fg_color="transparent",
            border_width=0,
            text_color="#ffffff"
        )
        self.user_input.grid(row=0, column=0, padx=(16, 5), pady=7, sticky="ew")
        self.user_input.bind("<Return>", lambda event: self.send_message())

        self.upload_button = ctk.CTkButton(
            self.input_pill, text="📁", command=self.upload_file, 
            fg_color="transparent", hover_color="#424242", text_color="#ffffff",
            width=36, height=36, corner_radius=18, font=("Segoe UI", 13)
        )
        self.upload_button.grid(row=0, column=1, padx=2, pady=7)

        self.mic_button = ctk.CTkButton(
            self.input_pill, text="🎤", command=self.listen_microphone, 
            fg_color="transparent", hover_color="#424242", text_color="#ffffff",
            width=36, height=36, corner_radius=18, font=("Segoe UI", 13)
        )
        self.mic_button.grid(row=0, column=2, padx=2, pady=7)

        self.send_button = ctk.CTkButton(
            self.input_pill, text="↑", command=self.send_message, 
            fg_color="#ffffff", hover_color="#d4d4d4", text_color="#000000",
            width=36, height=36, corner_radius=18, font=("Segoe UI", 16, "bold")
        )
        self.send_button.grid(row=0, column=3, padx=(2, 10), pady=7)

        # Load Session History & Render Canvas
        self.load_session_history(self.current_session_id)
        self.refresh_sidebar_sessions()

        # Register Global Hotkey listener (Ctrl + Space)
        self.register_global_hotkey()

    # ---------------- DYNAMIC PROGRAMMATIC RING ICON ----------------
    def set_dynamic_ring_icon(self):
        try:
            size = (64, 64)
            image = Image.new("RGBA", size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            # Draw bold white ring
            draw.ellipse([8, 8, 56, 56], outline=(255, 255, 255, 255), width=7)
            
            # Apply to top-level window icon
            icon_img = ctk.CTkImage(light_image=image, dark_image=image, size=(64, 64))
            self.iconphoto(True, icon_img._dark_image)
        except Exception as e:
            print(f"Dynamic Icon Error: {e}")

    # ---------------- ACTIVE BACKGROUND LISTENING ----------------
    def toggle_active_listening(self):
        if self.listen_switch.get() == 1:
            self.is_active_listening = True
            self.active_listener_thread = threading.Thread(target=self._background_listener_loop, daemon=True)
            self.active_listener_thread.start()
            messagebox.showinfo("Active Listening On", f"Listening in background! Say 'EV...' or '{self.agent_name}...' to issue commands.")
        else:
            self.is_active_listening = False

    def _background_listener_loop(self):
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = 300
        recognizer.dynamic_energy_threshold = True

        while self.is_active_listening:
            if self.is_speaking:
                time.sleep(0.5)
                continue

            try:
                with sr.Microphone() as source:
                    audio = recognizer.listen(source, timeout=3, phrase_time_limit=6)
                    try:
                        text = recognizer.recognize_google(audio).lower().strip()
                        print(f"[Background Heard]: {text}")

                        agent_kw = self.agent_name.lower()
                        wake_triggers = ["ev", "jean", agent_kw]
                        
                        has_wake_word = any(w in text for w in wake_triggers)
                        
                        if has_wake_word:
                            clean_cmd = re.sub(r'^(hey\s+)?(ev|jean|' + re.escape(agent_kw) + r')[\s,]*', '', text, flags=re.IGNORECASE).strip()
                            if clean_cmd:
                                self.after(0, lambda c=clean_cmd: self.handle_wake_command(c))
                        else:
                            if text.startswith(("open", "launch", "start", "remember", "memory")):
                                self.after(0, lambda c=text: self.handle_wake_command(c))

                    except sr.UnknownValueError:
                        pass
                    except sr.RequestError:
                        pass
            except Exception:
                time.sleep(1)

    def handle_wake_command(self, command):
        try:
            self.state('normal')
            self.deiconify()
            self.lift()
            self.focus_force()
            self.user_input.focus()

            self.user_input.delete(0, "end")
            self.user_input.insert(0, command)
            self.send_message()
        except Exception as e:
            print(f"Wake Command Handling Error: {e}")

    # ---------------- GLOBAL HOTKEY SETUP ----------------
    def register_global_hotkey(self):
        try:
            keyboard.add_hotkey('ctrl+space', self.toggle_window_focus)
        except Exception as e:
            print(f"Hotkey Registration Error: {e}")

    def toggle_window_focus(self):
        def _focus_task():
            try:
                self.state('normal')
                self.deiconify()
                self.attributes('-topmost', True)
                self.lift()
                self.focus_force()
                self.after(100, lambda: self.attributes('-topmost', False))
                self.user_input.focus()
            except Exception as e:
                print(f"Focus Window Error: {e}")
        
        self.after(0, _focus_task)

    # ---------------- DATABASE & SESSION SETUP ----------------
    def init_db(self):
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    role TEXT,
                    content TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS agent_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fact TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Database Init Error: {e}")

    def init_current_session(self):
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT session_id FROM messages ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            if row and row[0]:
                self.current_session_id = row[0]
            else:
                self.current_session_id = str(uuid.uuid4())
            conn.close()
        except Exception as e:
            print(f"Session Init Error: {e}")
            self.current_session_id = str(uuid.uuid4())

    def start_new_chat(self):
        self.current_session_id = str(uuid.uuid4())
        for widget in self.chat_container.winfo_children():
            widget.destroy()
        
        self.messages = [{"role": "system", "content": self.get_system_prompt()}]
        welcome_text = f"Hello {self.user_name}. I am {self.agent_name}. How can I assist you today?"
        self.add_message_bubble(self.agent_name, welcome_text, save_to_db=True)
        self.refresh_sidebar_sessions()
        self.speak(welcome_text)

    def load_settings(self):
        self.user_name = "Joel David"
        self.agent_name = "Jean"
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM settings")
            rows = cursor.fetchall()
            conn.close()

            settings_dict = {row[0]: row[1] for row in rows}
            if "user_name" in settings_dict:
                self.user_name = settings_dict["user_name"]
            if "agent_name" in settings_dict:
                self.agent_name = settings_dict["agent_name"]
        except Exception as e:
            print(f"Load Settings Error: {e}")

    def save_setting(self, key, value):
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Save Setting Error: {e}")

    def get_system_prompt(self):
        memories = self.fetch_agent_memories()
        memory_str = "\n".join([f"- {m}" for m in memories]) if memories else "None recorded yet."

        return f"""
You are {self.agent_name}, an AI collaborator who combines warm, engaging, and friendly conversation with sharp, structured logical thinking and expert technical guidance.

### User Context:
- User Name: {self.user_name}

### Agent Long-Term Memory (Facts stored by user):
{memory_str}
"""

    def open_settings_dialog(self):
        dialog_window = ctk.CTkToplevel(self)
        dialog_window.title("Customization Settings")
        dialog_window.geometry("380x280")
        dialog_window.grab_set()

        ctk.CTkLabel(dialog_window, text="Customize Names", font=("Segoe UI", 16, "bold")).pack(pady=(20, 10))

        ctk.CTkLabel(dialog_window, text="Your Username:", font=("Segoe UI", 12)).pack(anchor="w", padx=30)
        user_entry = ctk.CTkEntry(dialog_window, width=320, height=35, font=("Segoe UI", 13))
        user_entry.pack(padx=30, pady=(0, 10))
        user_entry.insert(0, self.user_name)

        ctk.CTkLabel(dialog_window, text="AI Agent Name:", font=("Segoe UI", 12)).pack(anchor="w", padx=30)
        agent_entry = ctk.CTkEntry(dialog_window, width=320, height=35, font=("Segoe UI", 13))
        agent_entry.pack(padx=30, pady=(0, 15))
        agent_entry.insert(0, self.agent_name)

        def save_changes():
            new_user = user_entry.get().strip()
            new_agent = agent_entry.get().strip()
            if new_user and new_agent:
                self.user_name = new_user
                self.agent_name = new_agent
                self.save_setting("user_name", new_user)
                self.save_setting("agent_name", new_agent)
                
                self.sidebar_brand.configure(text=f"✦ {self.agent_name} Workspace")
                self.user_input.configure(placeholder_text=f"Message {self.agent_name} or type 'open [app]'...")
                
                self.messages[0]["content"] = self.get_system_prompt()
                dialog_window.destroy()
                messagebox.showinfo("Updated", "Names updated successfully!")

        save_btn = ctk.CTkButton(dialog_window, text="Save Settings", command=save_changes, fg_color="#2f2f2f", hover_color="#3a3a3a", height=35)
        save_btn.pack(padx=30, pady=5, fill="x")

    # ---------------- ADVANCED SMART LAUNCHER ----------------
    def launch_system_target(self, target_query):
        clean_target = target_query.strip().lower()
        
        app_aliases = {
            "powerpoint": "powerpnt",
            "ppt": "powerpnt",
            "word": "winword",
            "docx": "winword",
            "excel": "excel",
            "spreadsheet": "excel",
            "notepad": "notepad.exe",
            "calculator": "calc.exe",
            "chrome": "chrome",
            "code": "code",
            "vscode": "code",
            "explorer": "explorer",
            "cmd": "cmd.exe",
            "powershell": "powershell.exe",
            "paint": "mspaint.exe",
            "settings": "ms-settings:"
        }

        try:
            if clean_target in app_aliases:
                exec_name = app_aliases[clean_target]
                subprocess.Popen(f'start {exec_name}', shell=True)
                return f"🚀 Opened application: `{target_query}`"

            if os.path.exists(target_query):
                os.startfile(target_query)
                return f"📂 Opened file/folder: `{target_query}`"

            start_menu_paths = [
                os.path.expanduser(r"~\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\**\*.lnk"),
                r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\**\*.lnk"
            ]
            
            matched_lnk = None
            for pattern in start_menu_paths:
                for lnk_file in glob.glob(pattern, recursive=True):
                    if clean_target in os.path.basename(lnk_file).lower():
                        matched_lnk = lnk_file
                        break
                if matched_lnk:
                    break

            if matched_lnk:
                os.startfile(matched_lnk)
                return f"🚀 Launched from Start Menu: `{os.path.basename(matched_lnk).replace('.lnk', '')}`"

            subprocess.Popen(f'start "" "{target_query}"', shell=True)
            return f"📂 Launched target: `{target_query}`"

        except Exception as e:
            return f"⚠️ Could not find or open '{target_query}'. Error: {e}"

    # ---------------- MEMORY MANAGEMENT ----------------
    def fetch_agent_memories(self):
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT fact FROM agent_memory")
            rows = cursor.fetchall()
            conn.close()
            return [row[0] for row in rows]
        except Exception as e:
            print(f"Fetch Memory Error: {e}")
            return []

    def save_agent_memory(self, fact):
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO agent_memory (fact) VALUES (?)", (fact,))
            conn.commit()
            conn.close()
            self.populate_agent_memory()
            self.messages[0]["content"] = self.get_system_prompt()
        except Exception as e:
            print(f"Save Memory Error: {e}")

    def delete_agent_memory(self, fact):
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM agent_memory WHERE fact=?", (fact,))
            conn.commit()
            conn.close()
            self.populate_agent_memory()
            self.messages[0]["content"] = self.get_system_prompt()
        except Exception as e:
            print(f"Delete Memory Error: {e}")

    def populate_agent_memory(self):
        for widget in self.memory_frame.winfo_children():
            widget.destroy()

        header = ctk.CTkLabel(
            self.memory_frame, text="🧠 Long-Term Agent Brain:", font=("Segoe UI", 13, "bold"),
            justify="left", text_color="#ffffff"
        )
        header.pack(padx=5, pady=(5, 10), anchor="w")

        memories = self.fetch_agent_memories()
        if not memories:
            empty_lbl = ctk.CTkLabel(
                self.memory_frame, text="(Type 'memory: [fact]' or 'remember: [fact]' in chat to store facts here)", 
                font=("Segoe UI", 11, "italic"), text_color="#888888", wraplength=220, justify="left"
            )
            empty_lbl.pack(padx=5, pady=2, anchor="w")
        else:
            for fact in memories:
                row_frame = ctk.CTkFrame(self.memory_frame, fg_color="transparent")
                row_frame.pack(fill="x", pady=2)
                row_frame.grid_columnconfigure(0, weight=1)

                fact_lbl = ctk.CTkLabel(
                    row_frame, text=f"• {fact}", font=("Segoe UI", 12),
                    justify="left", wraplength=190, text_color="#00e5ff"
                )
                fact_lbl.grid(row=0, column=0, sticky="w")

                del_btn = ctk.CTkButton(
                    row_frame, text="✕", width=22, height=22, font=("Segoe UI", 9, "bold"),
                    fg_color="transparent", hover_color="#5a2a2a", text_color="#ff6b6b",
                    corner_radius=4, command=lambda f=fact: self.delete_agent_memory(f)
                )
                del_btn.grid(row=0, column=1, padx=2)

    # ---------------- SESSION DATABASE & HISTORY ----------------
    def save_message_to_db(self, role, content):
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)", (self.current_session_id, role, content))
            conn.commit()
            conn.close()
            self.refresh_sidebar_sessions()
        except Exception as e:
            print(f"Database Save Error: {e}")

    def load_session_history(self, session_id):
        self.current_session_id = session_id
        self.messages = [{"role": "system", "content": self.get_system_prompt()}]
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT role, content FROM messages WHERE session_id=?", (session_id,))
            rows = cursor.fetchall()
            conn.close()

            for role, content in rows:
                self.messages.append({"role": role, "content": content})
        except Exception as e:
            print(f"Load Session Error: {e}")

        for widget in self.chat_container.winfo_children():
            widget.destroy()

        history_to_display = self.messages[1:]
        if not history_to_display:
            welcome_text = f"Hello {self.user_name}. I am {self.agent_name}. How can I assist you today?"
            self.add_message_bubble(self.agent_name, welcome_text, save_to_db=True)
        else:
            for msg in history_to_display:
                sender = self.agent_name if msg["role"] == "assistant" else self.user_name
                self.add_message_bubble(sender, msg["content"], save_to_db=False)
        self.refresh_sidebar_sessions()

    def delete_session(self, session_id):
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
            conn.commit()
            conn.close()

            self.refresh_sidebar_sessions()
            if self.current_session_id == session_id:
                self.start_new_chat()
        except Exception as e:
            print(f"Delete Session Error: {e}")

    def refresh_sidebar_sessions(self):
        for widget in self.history_frame.winfo_children():
            widget.destroy()

        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT COALESCE(session_id, 'default_session'), content FROM messages WHERE role='user' GROUP BY COALESCE(session_id, 'default_session') ORDER BY id DESC")
            sessions = cursor.fetchall()
            conn.close()

            for sess_id, content in sessions:
                snippet = content[:22] + "..." if len(content) > 22 else content
                
                row_frame = ctk.CTkFrame(self.history_frame, fg_color="transparent")
                row_frame.pack(fill="x", pady=2)
                row_frame.grid_columnconfigure(0, weight=1)

                btn = ctk.CTkButton(
                    row_frame, text=f"💬 {snippet}", font=("Segoe UI", 12),
                    fg_color="#282828" if sess_id == self.current_session_id else "transparent",
                    hover_color="#333333", text_color="#ffffff" if sess_id == self.current_session_id else "#cccccc",
                    anchor="w", height=32, corner_radius=6,
                    command=lambda s=sess_id: self.load_session_history(s)
                )
                btn.grid(row=0, column=0, sticky="ew")

                del_btn = ctk.CTkButton(
                    row_frame, text="✕", width=24, height=24, font=("Segoe UI", 10, "bold"),
                    fg_color="transparent", hover_color="#5a2a2a", text_color="#ff6b6b",
                    corner_radius=4, command=lambda s=sess_id: self.delete_session(s)
                )
                del_btn.grid(row=0, column=1, padx=2)
        except Exception as e:
            print(f"Sessions Refresh Error: {e}")

    def populate_user_summary(self):
        for widget in self.summary_frame.winfo_children():
            widget.destroy()

        base_sections = [
            (f"👤 User Profile: {self.user_name}", True),
            ("• Status: Final-Year B.Tech CS Student", False),
            ("• Location: Kerala, India", False),
            ("• Tech Stack: Python, C++, Java, Flutter, Django, SQL", False),
            ("\n🚀 Active Projects:", True),
            ("1. ResQConnect: Off-grid disaster mesh network using ESP32, LoRa, and Flutter.", False),
            (f"2. Jennie / {self.agent_name}: Python desktop AI assistant with local Ollama integration.", False)
        ]

        for text, is_bold in base_sections:
            font_style = ("Segoe UI", 13, "bold") if is_bold else ("Segoe UI", 12)
            lbl = ctk.CTkLabel(
                self.summary_frame, text=text, font=font_style,
                justify="left", wraplength=220, text_color="#ffffff" if is_bold else "#dddddd"
            )
            lbl.pack(padx=5, pady=2, anchor="w")

    def fetch_web_search(self, query):
        try:
            with DDGS() as ddgs:
                results = [r for r in ddgs.text(query, max_results=3)]
                if results:
                    search_summary = "\n[Live Web Search Results:]\n"
                    for r in results:
                        search_summary += f"- Title: {r.get('title')}\n  Snippet: {r.get('body')}\n  URL: {r.get('href')}\n"
                    return search_summary
        except Exception as e:
            print(f"Web Search Error: {e}")
        return ""

    def toggle_mute(self):
        self.is_muted = not self.is_muted
        if self.is_muted:
            self.mute_button.configure(text="🔇 Muted", text_color="#ef4444")
            if self.tts_engine:
                try:
                    self.tts_engine.stop()
                except Exception:
                    pass
        else:
            self.mute_button.configure(text="🔊 Voice", text_color="#ececec")

    def speak(self, text):
        if not self.is_muted:
            threading.Thread(target=self._run_tts, args=(text,), daemon=True).start()

    def _run_tts(self, text):
        try:
            self.is_speaking = True
            self.tts_engine = pyttsx3.init()
            self.tts_engine.setProperty('rate', 145)
            self.tts_engine.setProperty('volume', 0.95)
            
            voices = self.tts_engine.getProperty('voices')
            selected_voice = None
            
            for voice in voices:
                voice_info = voice.name.lower()
                if any(name in voice_info for name in ["hazel", "zira", "female"]):
                    selected_voice = voice.id
                    break
            
            if not selected_voice and voices:
                selected_voice = voices[0].id
                
            if selected_voice:
                self.tts_engine.setProperty('voice', selected_voice)

            clean_text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
            clean_text = re.sub(r'`[^`]*`', '', clean_text)
            clean_text = re.sub(r'\*\*(.*?)\*\*', r'\1', clean_text)
            clean_text = clean_text.replace('#', '').replace('*', '').replace('---', '')
            clean_text = clean_text.replace('  ', ' ')

            if clean_text.strip() and not self.is_muted:
                self.tts_engine.say(clean_text)
                self.tts_engine.runAndWait()
                self.tts_engine.stop()
        except Exception as e:
            print(f"Speech Error: {e}")
        finally:
            self.is_speaking = False
            self.tts_engine = None

    def upload_file(self):
        file_path = filedialog.askopenfilename(
            title="Select a file for AI to analyze",
            filetypes=[("Text & Code Files", "*.txt *.py *.js *.html *.css *.json *.md *.cpp *.java"), ("All Files", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                filename = os.path.basename(file_path)
                self.attached_file_content = f"\n\n[Attached File: {filename}]\n```\n{content}\n```"
                self.user_input.delete(0, "end")
                self.user_input.insert(0, f"Analyze this file: {filename}")
                messagebox.showinfo("File Attached", f"Successfully loaded '{filename}'. Now type your request and hit Send!")
            except Exception as e:
                messagebox.showerror("Error", f"Could not read file: {e}")

    def listen_microphone(self):
        def _listen_task():
            recognizer = sr.Recognizer()
            try:
                with sr.Microphone() as source:
                    self.after(0, lambda: self.user_input.delete(0, "end"))
                    self.after(0, lambda: self.user_input.insert(0, "Listening... Speak now..."))
                    recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    audio = recognizer.listen(source, timeout=5, phrase_time_limit=15)
                    text = recognizer.recognize_google(audio)
                    self.after(0, lambda: self.user_input.delete(0, "end"))
                    self.after(0, lambda: self.user_input.insert(0, text))
            except sr.UnknownValueError:
                self.after(0, lambda: self.user_input.delete(0, "end"))
                messagebox.showwarning("Voice Input", "Could not understand audio clearly. Please try again.")
            except Exception as e:
                self.after(0, lambda: self.user_input.delete(0, "end"))
                messagebox.showerror("Microphone Error", f"Speech recognition failed. Ensure PyAudio is installed.\nDetails: {e}")

        threading.Thread(target=_listen_task, daemon=True).start()

    def send_message(self):
        query = self.user_input.get().strip()
        if not query and not self.attached_file_content:
            return

        memory_match = re.search(r'^(?:memory|remember)[:\s]+(.+)', query, re.IGNORECASE)
        if memory_match:
            fact_content = memory_match.group(1).strip()
            self.save_agent_memory(fact_content)
            
            confirmation_msg = f"Got it, {self.user_name}! I have stored '{fact_content}' into my long-term **Agent Memory** brain."
            self.add_message_bubble(self.user_name, query, save_to_db=True)
            self.add_message_bubble(self.agent_name, confirmation_msg, save_to_db=True)
            self.speak("Got it! I have saved that fact to my memory.")
            self.user_input.delete(0, "end")
            return

        open_match = re.search(r'^(?:open|launch|start)\s+(?:app|file|document)?\s*(.+)', query, re.IGNORECASE)
        if open_match:
            target = open_match.group(1).strip()
            launch_result = self.launch_system_target(target)
            
            self.add_message_bubble(self.user_name, query, save_to_db=True)
            self.add_message_bubble(self.agent_name, launch_result, save_to_db=True)
            self.speak(f"Opening {target}")
            self.user_input.delete(0, "end")
            return

        display_query = query + (f" [Attached File Content Included]" if self.attached_file_content else "")

        search_keywords = ["latest", "news", "today", "current", "price", "weather", "who is", "what happened", "2026"]
        needs_search = any(kw in query.lower() for kw in search_keywords)

        full_query = query + self.attached_file_content
        if needs_search:
            web_data = self.fetch_web_search(query)
            if web_data:
                full_query += f"\n\n{web_data}\n(Note: Use the live search results above to provide an accurate, up-to-date answer)."

        self.attached_file_content = ""

        self.add_message_bubble(self.user_name, display_query, save_to_db=True)
        self.messages.append({"role": "user", "content": full_query})

        self.user_input.delete(0, "end")
        self.send_button.configure(state="disabled")

        threading.Thread(target=self._fetch_response, daemon=True).start()

    def _fetch_response(self):
        reply = ""
        try:
            response = ollama.chat(
                model=OLLAMA_MODEL,
                messages=self.messages
            )
            reply = response['message']['content']
            self.messages.append({"role": "assistant", "content": reply})
            self.save_message_to_db("assistant", reply)

        except Exception as e:
            reply = (
                f"⚠️ **Error connecting to Ollama:** {e}\n\n"
                f"Please make sure Ollama is active (`ollama run {OLLAMA_MODEL}`)."
            )

        self.after(0, lambda: self.add_message_bubble(self.agent_name, reply, save_to_db=False))
        self.after(0, lambda: self.send_button.configure(state="normal"))

        if "⚠️" not in reply:
            self.speak(reply)

    def add_message_bubble(self, sender, text, save_to_db=False):
        if save_to_db:
            role = "user" if sender == self.user_name else "assistant"
            self.save_message_to_db(role, text)

        is_agent = (sender == self.agent_name)
        frame_color = "#212121" if is_agent else "#2f2f2f"

        msg_frame = ctk.CTkFrame(self.chat_container, fg_color=frame_color, corner_radius=12)
        msg_frame.pack(fill="x", padx=20, pady=10, anchor="w")
        msg_frame.grid_columnconfigure(0, weight=1)

        header_bar = ctk.CTkFrame(msg_frame, fg_color="transparent")
        header_bar.pack(fill="x", padx=16, pady=(10, 4))

        sender_label = ctk.CTkLabel(
            header_bar, 
            text=f"✦ {self.agent_name}" if is_agent else f"👤 {self.user_name}", 
            font=("Segoe UI", 13, "bold"), 
            text_color="#ffffff" if is_agent else "#cccccc"
        )
        sender_label.pack(side="left")

        actions_frame = ctk.CTkFrame(header_bar, fg_color="transparent")
        actions_frame.pack(side="right")

        speak_btn = ctk.CTkButton(
            actions_frame, text="🔊", width=28, height=24, font=("Segoe UI", 11),
            fg_color="transparent", hover_color="#3d3d3d", text_color="#cccccc",
            command=lambda t=text: self.speak(t)
        )
        speak_btn.pack(side="left", padx=2)

        copy_msg_btn = ctk.CTkButton(
            actions_frame, text="📋", width=28, height=24, font=("Segoe UI", 11),
            fg_color="transparent", hover_color="#3d3d3d", text_color="#cccccc",
            command=lambda t=text: self.copy_to_clipboard(t, "Message copied to clipboard!")
        )
        copy_msg_btn.pack(side="left", padx=2)

        if not is_agent:
            content_label = ctk.CTkLabel(
                msg_frame, text=text, font=("Segoe UI", 14), 
                wraplength=750, justify="left", text_color="#f3f3f3"
            )
            content_label.pack(anchor="w", padx=16, pady=(0, 14))
        else:
            parts = self.parse_markdown_code_blocks(text)
            for part_type, content in parts:
                if part_type == "text":
                    if content.strip():
                        cleaned_display_text = re.sub(r'\*\*(.*?)\*\*', r'\1', content.strip())
                        cleaned_display_text = cleaned_display_text.replace('---', '')

                        lbl = ctk.CTkLabel(
                            msg_frame, text=cleaned_display_text, font=("Segoe UI", 14), 
                            wraplength=750, justify="left", text_color="#ececec"
                        )
                        lbl.pack(anchor="w", padx=16, pady=4)
                elif part_type == "code":
                    lang, code_text = content

                    code_frame = ctk.CTkFrame(msg_frame, fg_color="#181818", corner_radius=8)
                    code_frame.pack(fill="x", padx=16, pady=8, expand=True)
                    code_frame.grid_columnconfigure(0, weight=1)

                    header_frame = ctk.CTkFrame(code_frame, fg_color="#282828", corner_radius=6, height=32)
                    header_frame.pack(fill="x", padx=2, pady=2)

                    lang_lbl = ctk.CTkLabel(header_frame, text=lang.upper(), font=("Consolas", 11, "bold"), text_color="#999999")
                    lang_lbl.pack(side="left", padx=12)

                    copy_code_btn = ctk.CTkButton(
                        header_frame, text="Copy code", width=75, height=22, font=("Segoe UI", 11),
                        fg_color="transparent", hover_color="#3a3a3a", text_color="#cccccc",
                        command=lambda c=code_text: self.copy_to_clipboard(c, "Code copied successfully!")
                    )
                    copy_code_btn.pack(side="right", padx=6, pady=3)

                    line_count = len(code_text.splitlines())
                    box_height = min(max(line_count * 20, 60), 220)

                    code_box = ctk.CTkTextbox(
                        code_frame, wrap="none", font=("Consolas", 12), height=box_height,
                        fg_color="#181818", text_color="#f8f8f2"
                    )
                    code_box.pack(fill="x", padx=8, pady=(0, 8))
                    code_box.insert("1.0", code_text)
                    code_box.configure(state="disabled")

        self.chat_container._parent_canvas.yview_moveto(1.0)

    def parse_markdown_code_blocks(self, text):
        pattern = r"```([a-zA-Z0-9_-]*)\n(.*?)```"
        parts = []
        last_end = 0
        for match in re.finditer(pattern, text, re.DOTALL):
            start, end = match.span()
            if start > last_end:
                parts.append(("text", text[last_end:start]))
            lang = match.group(1) or "code"
            code = match.group(2)
            parts.append(("code", (lang, code)))
            last_end = end
        if last_end < len(text):
            parts.append(("text", text[last_end:]))
        return parts

    def copy_to_clipboard(self, text, message):
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Copied!", message)

    def copy_full_chat(self):
        full_transcript = ""
        for msg in self.messages:
            if msg["role"] == "user":
                full_transcript += f"{self.user_name}:\n{msg['content']}\n\n" + "-"*50 + "\n\n"
            elif msg["role"] == "assistant":
                full_transcript += f"{self.agent_name}:\n{msg['content']}\n\n" + "-"*50 + "\n\n"

        if not full_transcript.strip():
            messagebox.showwarning("Empty", "No chat history to copy yet!")
            return

        self.copy_to_clipboard(full_transcript, "Full conversation transcript copied to clipboard!")

if __name__ == "__main__":
    app = JeanDesktopApp()
    app.mainloop()