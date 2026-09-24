"""Native, staged Windows setup with responsive database and hosting operations.

All service calls run on one worker. Tk state is read and written only on the
main thread. Passwords stay in memory until the service saves the game account;
they are never copied into diagnostics by this UI.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Empty, Queue
import sys

from tools.setup_diagnostics import SETUP_VERSION, SetupFailure

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:  # Console setup remains available without the optional GUI.
    tk = ttk = None


class WizardUnavailable(RuntimeError):
    """A graphical desktop or Tcl/Tk installation is not available."""


def _port(value, label):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number from 1 to 65535.") from None
    if not 1 <= number <= 65535:
        raise ValueError(f"{label} must be a number from 1 to 65535.")
    return number


def _single_line(value):
    return isinstance(value, str) and not any(ord(c) < 32 or ord(c) == 127 for c in value)


def _windows_dpi():
    if sys.platform != "win32":
        return
    import ctypes
    try:
        fn = ctypes.windll.user32.SetProcessDpiAwarenessContext
        fn.argtypes = [ctypes.c_void_p]
        fn.restype = ctypes.c_bool
        if fn(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


class SetupWizard:
    """The view accepts a service instance, allowing actual Tk regression tests."""

    STEPS = ("Database server", "Game database", "Connection kit", "Ready")
    BG = "#0b1220"
    PANEL = "#131f32"
    TEXT = "#edf4fc"
    MUTED = "#afbed0"
    ACCENT = "#5ee1d3"
    FONT = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"

    def __init__(self, window, service, initial_stage="database"):
        self.window, self.service = window, service
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nxt-setup")
        self.events = Queue()
        self.busy = False
        self.closed = False
        self.exit_code = 1
        self.page_index = 0
        self.database_ready = False
        self.hosting_ready = False
        self.kit_path = None
        self.last_retry = None
        self._controls = []
        self._wrap_labels = []
        self._focus_targets = []
        startup_error = None
        try:
            self.defaults = service.defaults()
        except Exception as error:
            self.defaults = {}
            startup_error = error
        self.values = {key: tk.StringVar(window, value=str(self.defaults.get(key, fallback)))
                       for key, fallback in {
                           "host": "127.0.0.1", "port": 3307, "name": "digimon_venom_nxt",
                           "user": "venom_nxt",
                           "account_host": "127.0.0.1", "public_host": "localhost",
                           "game_port": 8765, "bind": "0.0.0.0"}.items()}
        # Passwords are deliberately not populated from saved settings.
        self.values["password"] = tk.StringVar(window)
        public = self.values["public_host"].get()
        self.connection_mode = tk.StringVar(window, value="local" if public in ("", "localhost", "127.0.0.1", "::1") else "online")
        self.status = tk.StringVar(window, value="Prepare the MySQL process stored inside this server folder.")
        self.database_result = tk.StringVar(window, value="")
        self.ready_summary = tk.StringVar(window, value="")
        self._style()
        self._build()
        self._show_page(2 if initial_stage in ("hosting", "public", "connection") else 0)
        if self.page_index == 2:
            self.status.set("Create a connection kit using the saved game database settings.")
        if startup_error is not None:
            self._handle_failure(startup_error, None)
        self._poll_after = self.window.after(60, self._poll)

    def _style(self):
        window = self.window
        window.title(f"Digimon Venom NXT | Server setup {SETUP_VERSION}")
        window.configure(bg=self.BG)
        style = ttk.Style(window)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(".", font=(self.FONT, 11), background=self.BG, foreground=self.TEXT)
        style.configure("TFrame", background=self.BG)
        style.configure("Panel.TFrame", background=self.PANEL)
        style.configure("TLabel", background=self.BG, foreground=self.TEXT)
        style.configure("Muted.TLabel", foreground=self.MUTED)
        style.configure("Title.TLabel", font=(self.FONT, 23, "bold"))
        style.configure("Section.TLabel", font=(self.FONT, 18, "bold"))
        style.configure("Brand.TLabel", font=(self.FONT, 10, "bold"), foreground=self.ACCENT)
        style.configure("Step.TLabel", font=(self.FONT, 10), foreground=self.MUTED)
        style.configure("Active.Step.TLabel", foreground=self.ACCENT, font=(self.FONT, 10, "bold"))
        style.configure("TButton", padding=(13, 9), background="#253853", foreground=self.TEXT, borderwidth=0)
        style.map("TButton", background=[("active", "#345171"), ("disabled", "#1b283d")], foreground=[("disabled", "#78879d")])
        style.configure("Accent.TButton", background=self.ACCENT, foreground="#071c21", font=(self.FONT, 11, "bold"))
        style.map("Accent.TButton", background=[("active", "#8deee3"), ("disabled", "#284d51")], foreground=[("disabled", "#a0b7bb")])
        style.configure("TEntry", fieldbackground="#1a2a42", foreground=self.TEXT, padding=8, insertcolor=self.TEXT, borderwidth=1)
        style.map("TEntry", fieldbackground=[("disabled", "#172337")], foreground=[("disabled", "#91a3bb")])
        style.configure("TCheckbutton", padding=(0, 7), background=self.BG, foreground=self.MUTED)
        style.map("TCheckbutton", background=[("active", self.BG)], foreground=[("active", self.TEXT), ("disabled", "#78879d")])
        style.configure("TRadiobutton", padding=(0, 8), background=self.BG, foreground=self.TEXT)
        style.map("TRadiobutton", background=[("active", self.BG)])
        style.configure("Horizontal.TProgressbar", background=self.ACCENT, troughcolor="#23344b", borderwidth=0)
        # Points scale with display DPI; geometry also scales to keep text and fields together.
        factor = max(1.0, float(window.tk.call("tk", "scaling")) / (96 / 72))
        screen_w, screen_h = window.winfo_screenwidth(), window.winfo_screenheight()
        width = min(int(840 * factor), max(640, screen_w - 70))
        height = min(int(900 * factor), max(480, screen_h - 110))
        window.geometry(f"{width}x{height}+{max(0, (screen_w-width)//2)}+{max(0, (screen_h-height)//2)}")
        window.minsize(min(int(640 * factor), width), min(int(480 * factor), height))

    def _build(self):
        window = self.window
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)
        header = ttk.Frame(window, padding=(26, 20, 26, 12))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=f"DIGIMON VENOM NXT  /  SETUP {SETUP_VERSION}", style="Brand.TLabel").grid(sticky="w")
        ttk.Label(header, text="Set up your server", style="Title.TLabel").grid(sticky="w", pady=(3, 13))
        steps = ttk.Frame(header)
        steps.grid(sticky="ew")
        self.step_labels = []
        for index, title in enumerate(self.STEPS):
            steps.columnconfigure(index, weight=1)
            label = ttk.Label(steps, text=f"{index+1}. {title}", style="Step.TLabel")
            label.grid(row=0, column=index, sticky="w", padx=(0, 8))
            self.step_labels.append(label)
        holder = ttk.Frame(window)
        holder.grid(row=1, column=0, sticky="nsew")
        holder.columnconfigure(0, weight=1)
        holder.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(holder, bg=self.BG, highlightthickness=0, bd=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(holder, orient="vertical", command=self.canvas.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=scroll.set)
        self.body = ttk.Frame(self.canvas, padding=(26, 14, 18, 18))
        self.body.columnconfigure(0, weight=1)
        self.body_window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.bind("<Configure>", self._resize)
        self.body.bind("<Configure>", lambda _: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        window.bind_all("<MouseWheel>", self._wheel)
        window.bind_all("<Button-4>", self._wheel)
        window.bind_all("<Button-5>", self._wheel)
        self.pages = []
        for _ in self.STEPS:
            page = ttk.Frame(self.body)
            page.columnconfigure(0, weight=1)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages.append(page)
        self._database_page()
        self._account_page()
        self._hosting_page()
        self._ready_page()
        self.error_frame = ttk.Frame(self.body, padding=(0, 16, 0, 0))
        self.error_frame.grid(row=1, column=0, sticky="ew")
        self.error_frame.columnconfigure(0, weight=1)
        self.error_title = tk.StringVar(window)
        ttk.Label(self.error_frame, textvariable=self.error_title, foreground="#ffb5b5", font=(self.FONT, 12, "bold")).grid(sticky="w")
        self.error_text = tk.Text(self.error_frame, height=8, wrap="word", bg="#281d2a", fg="#ffe0e0", relief="flat", padx=12, pady=10, font=(self.FONT, 10), state="disabled", takefocus=True)
        self.error_text.grid(sticky="ew", pady=(8, 10))
        self.report_location = tk.StringVar(window)
        location = ttk.Label(self.error_frame, textvariable=self.report_location, style="Muted.TLabel", wraplength=740, justify="left")
        location.grid(sticky="ew", pady=(0, 10))
        self._wrap_labels.append(location)
        self.retry_button = ttk.Button(self.error_frame, text="Retry this step", command=self._retry)
        self.retry_button.grid(sticky="w")
        self.error_frame.grid_remove()
        footer = ttk.Frame(window, padding=(26, 10, 26, 18))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(footer, mode="indeterminate")
        self.progress.grid(row=0, column=0, sticky="ew", pady=(0, 9))
        status_label = ttk.Label(footer, textvariable=self.status, style="Muted.TLabel", wraplength=730, justify="left")
        status_label.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        self._wrap_labels.append(status_label)
        nav = ttk.Frame(footer)
        nav.grid(row=2, column=0, sticky="ew")
        nav.columnconfigure(1, weight=1)
        self.back = ttk.Button(nav, text="Back", command=self._back)
        self.back.grid(row=0, column=0, sticky="w")
        self.copy_button = ttk.Button(nav, text="Copy report", command=self._copy_report)
        self.copy_button.grid(row=0, column=1, sticky="w", padx=8)
        self.primary = ttk.Button(nav, text="Test connection", style="Accent.TButton", command=self._advance)
        self.primary.grid(row=0, column=3, sticky="e")
        window.protocol("WM_DELETE_WINDOW", self._close)
        window.bind("<Return>", self._return)
        window.bind("<Escape>", lambda _: self._close())

    def _label(self, parent, text, *, style="Muted.TLabel", pad=(0, 12)):
        label = ttk.Label(parent, text=text, style=style, wraplength=740, justify="left")
        label.pack(anchor="w", fill="x", pady=pad)
        self._wrap_labels.append(label)
        return label

    def _section(self, page, title, subtitle):
        content = ttk.Frame(page)
        content.grid(sticky="ew")
        self._label(content, title, style="Section.TLabel", pad=(0, 8))
        self._label(content, subtitle, pad=(0, 19))
        return content

    def _field(self, parent, label, key, *, note=None, password=False):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=(0, 12))
        ttk.Label(frame, text=label).pack(anchor="w", pady=(0, 5))
        entry = ttk.Entry(frame, textvariable=self.values[key], show="*" if password else "", font=(self.FONT, 11))
        entry.pack(fill="x")
        self._controls.append(entry)
        if password:
            entry.configure(validate="key", validatecommand=(self.window.register(_single_line), "%P"))
            controls = ttk.Frame(frame)
            controls.pack(fill="x", pady=(3, 0))
            revealed = tk.BooleanVar(self.window, value=False)
            show = ttk.Checkbutton(controls, text="Show password", variable=revealed,
                                   command=lambda: entry.configure(show="" if revealed.get() else "*"))
            show.pack(side="left")
            paste = ttk.Button(controls, text="Paste", command=lambda: self._paste(entry))
            paste.pack(side="left", padx=(16, 6))
            clear = ttk.Button(controls, text="Clear", command=lambda: self.values[key].set(""))
            clear.pack(side="left")
            self._controls.extend((show, paste, clear))
            entry.bind("<<Paste>>", lambda _: self._paste(entry))
        if note:
            self._label(frame, note, pad=(5, 0))
        return entry

    def _database_page(self):
        page = self._section(self.pages[0], "Your own portable MySQL", "The database runs as a separate process from this server folder. No database service installation or administrator password is needed.")
        self._label(page, "MySQL program: mysql/runtime", style="Section.TLabel", pad=(0, 12))
        self._label(page, "Player saves and database files: mysql/data")
        self._label(page, "Local database connection: 127.0.0.1:3307. The game uses its own TCP port, normally 8765.")
        self._label(page, "Prepare MySQL starts this folder's database and checks that it is ready. First setup creates a fresh database directory and private administrator credentials automatically.")
        self._label(page, "For a complete backup or a move to another PC, run STOP_SERVER.bat and wait for the clean shutdown confirmation, then copy or ZIP the entire server folder.")
        self._label(page, "Keep this server folder private. It contains all saved progress, database credentials and server keys.")
        self._focus_targets.append(None)

    def _account_page(self):
        page = self._section(self.pages[1], "Create the game database login", "Setup creates the account the dedicated server will use. You do not need an existing game account or password.")
        success = ttk.Label(page, textvariable=self.database_result, foreground=self.ACCENT, wraplength=740, justify="left")
        success.pack(fill="x", pady=(0, 18))
        self._wrap_labels.append(success)
        first = self._field(page, "Game database name", "name", note="Keep this name when upgrading to preserve the same players and progress.")
        self._field(page, "Game database username", "user", note="This dedicated login belongs to this installation. Keep its saved name on later setup checks.")
        self._field(page, "Choose a game database password (optional)", "password", password=True,
                    note="Leave blank for automatic setup: a strong password is generated for a new login, or the saved game password is kept for an existing installation.")
        self._label(page, "The game login is restricted to this PC. Database credentials are managed within this server folder.")
        self._label(page, "The game login is saved in the server configuration. Players create their own in-game accounts separately.")
        self._focus_targets.append(first)

    def _hosting_page(self):
        page = self._section(self.pages[2], "Choose how players connect", "Create the server certificate and matching client connection kit together.")
        local = ttk.Radiobutton(page, text="Local play on this PC", value="local", variable=self.connection_mode, command=self._hosting_mode)
        local.pack(anchor="w")
        online = ttk.Radiobutton(page, text="LAN or online players", value="online", variable=self.connection_mode, command=self._hosting_mode)
        online.pack(anchor="w", pady=(0, 10))
        self._controls.extend((local, online))
        self._field(page, "Server address for players", "public_host", note="Local: localhost. LAN: this PC's LAN IP. Online: your public hostname or public IP, without http:// or a port.")
        self._field(page, "Game TCP port", "game_port", note="Default 8765. Allow this port through Windows Firewall; forward it on your router for internet players.")
        self._field(page, "Listen address", "bind", note="127.0.0.1 is this PC only. Use 0.0.0.0 to accept LAN or internet connections.")
        self._label(page, "Distribute the generated client kit with your client. Keep the server's private key and database configuration on the server PC.")
        self._label(page, "Your database is already saved after step 2. You can close this window and return to connection setup later using step 03.")
        self._focus_targets.append(local)
        if self.connection_mode.get() == "local":
            self._hosting_mode()

    def _ready_page(self):
        page = self._section(self.pages[3], "Setup verified", "Your saved configuration has passed the checks below.")
        self.ready_label = ttk.Label(page, textvariable=self.ready_summary, wraplength=740, justify="left", foreground=self.ACCENT, font=(self.FONT, 12))
        self.ready_label.pack(fill="x", pady=(0, 22))
        self._wrap_labels.append(self.ready_label)
        self._label(page, "Next steps", style="Section.TLabel", pad=(0, 10))
        self.next_steps = tk.StringVar(self.window)
        next_label = ttk.Label(page, textvariable=self.next_steps, wraplength=740, justify="left")
        next_label.pack(fill="x")
        self._wrap_labels.append(next_label)
        self._focus_targets.append(None)

    def _resize(self, event):
        self.canvas.itemconfigure(self.body_window, width=event.width)
        wrap = max(240, event.width - 66)
        for label in self._wrap_labels:
            label.configure(wraplength=wrap)

    def _wheel(self, event):
        # Scroll only events in this wizard; keyboard focus in entries is preserved.
        if event.widget.winfo_toplevel() != self.window:
            return
        if getattr(event, "num", None) == 4:
            units = -3
        elif getattr(event, "num", None) == 5:
            units = 3
        else:
            delta = getattr(event, "delta", 0)
            units = -int(delta / 120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
        if self.canvas.bbox("all") and self.canvas.bbox("all")[3] > self.canvas.winfo_height():
            self.canvas.yview_scroll(units, "units")

    def _paste(self, entry):
        if self.busy:
            return "break"
        try:
            value = self.window.clipboard_get()
        except tk.TclError:
            self.status.set("The clipboard does not contain text.")
            return "break"
        if not _single_line(value):
            self.status.set("Paste a single-line password. Nothing was pasted.")
            return "break"
        if entry.selection_present():
            entry.delete("sel.first", "sel.last")
        entry.insert("insert", value)
        entry.focus_set()
        self.status.set("Password pasted. Spaces and punctuation are kept exactly.")
        return "break"

    def _hosting_mode(self):
        if self.connection_mode.get() == "local":
            self.values["public_host"].set("localhost")
            self.values["bind"].set("127.0.0.1")
        else:
            self.values["bind"].set("0.0.0.0")
            if self.values["public_host"].get() in ("localhost", "127.0.0.1", "::1"):
                self.values["public_host"].set("")

    def _show_page(self, index):
        self.page_index = index
        for number, page in enumerate(self.pages):
            page.grid() if number == index else page.grid_remove()
            self.step_labels[number].configure(style="Active.Step.TLabel" if number == index else "Step.TLabel")
        self.back.configure(state="normal" if index in (1, 2) else "disabled")
        self.primary.configure(text=("Prepare MySQL", "Create game database", "Create connection kit", "Finish")[index])
        self.canvas.yview_moveto(0)
        focus = self._focus_targets[index] or self.primary
        self.window.after_idle(focus.focus_set)

    def _back(self):
        if not self.busy and self.page_index in (1, 2):
            self.error_frame.grid_remove()
            self._show_page(self.page_index - 1)

    def _return(self, event):
        # A focused button/check box should receive its own keyboard activation.
        if isinstance(event.widget, (ttk.Button, ttk.Checkbutton, ttk.Radiobutton)):
            return
        self._advance()
        return "break"

    def _advance(self):
        if not self.busy:
            (self._test_database, self._configure_database, self._configure_hosting, self._finish)[self.page_index]()

    def _database_settings(self):
        return {"name": self.values["name"].get().strip(),
                "user": self.values["user"].get().strip(),
                "password": self.values["password"].get()}

    def _validation(self, action):
        try:
            return action()
        except ValueError as error:
            self._failure("Check your settings", str(error), None)
            return None

    def _test_database(self):
        settings = self._validation(self._database_settings)
        if settings is None:
            return
        def success(result):
            version = result.get("server_version", "MySQL")
            self.database_result.set(f"Portable {version} is ready\nSaves: mysql/data | {result.get('host', '127.0.0.1')}:{result.get('port', 3307)}")
            self.status.set("Portable MySQL verified. Now create the game database.")
            self._show_page(1)
        self._submit("Preparing portable MySQL… First initialization can take a few minutes.", lambda: self.service.test_database(settings), success, self._test_database)

    def _configure_database(self):
        settings = self._validation(self._database_settings)
        if settings is None:
            return
        def success(result):
            self.database_ready = True
            self.values["user"].set(result.get("user", settings["user"]))
            self.status.set(f"Game database ready: {result.get('name', settings['name'])}. Your game login was saved successfully.")
            self._show_page(2)
        self._submit("Creating and verifying the game database… Keep this window open.", lambda: self.service.configure_database(settings), success, self._configure_database)

    def _configure_hosting(self):
        def settings_from_fields():
            settings = {"host": self.values["public_host"].get().strip(), "port": _port(self.values["game_port"].get(), "Game port"), "bind": self.values["bind"].get().strip()}
            if not settings["host"] or not settings["bind"]:
                raise ValueError("Enter the server address players will use and a listen address.")
            if "://" in settings["host"] or "/" in settings["host"]:
                raise ValueError("Use a hostname or IP address without http://, https://, or a path.")
            return settings
        settings = self._validation(settings_from_fields)
        if settings is None:
            return
        def success(path):
            self.hosting_ready = True
            self.kit_path = Path(path)
            self._verify()
        self._submit("Creating the server certificate and client connection kit…", lambda: self.service.configure_hosting(settings), success, self._configure_hosting)

    def _verify(self):
        def success(result):
            self.database_ready = True
            self.exit_code = 0
            details = ["Database connection and saved game login verified."]
            address = result.get("host", self.values["public_host"].get())
            port = result.get("port", self.values["game_port"].get())
            kit = result.get("player_kit", self.kit_path)
            details.extend([f"Player address: {address}:{port}", f"Client connection kit: {kit}"])
            if result.get("tls"):
                details.append(f"Certificate connection verified: {result['tls']}")
            self.next_steps.set("1. Start MySQL with START_MYSQL.bat, then launch START_WORLD_SERVER_CONSOLE.bat.\n\n2. Extract the generated connection ZIP into each player's client folder. Its config folder must merge with the client's config folder.\n\n3. Launch the client and create your player account. For online play, allow and forward the game TCP port shown above.")
            if result.get("note"):
                details.append(str(result["note"]))
            self.ready_summary.set("\n\n".join(details))
            self.status.set("Setup complete. You can close this window.")
            self._show_page(3)
        self._submit("Verifying the saved server configuration…", self.service.verify_installation, success, self._verify)

    def _set_busy(self, busy):
        self.busy = busy
        state = "disabled" if busy else "normal"
        for control in self._controls + [self.back, self.primary, self.retry_button]:
            control.configure(state=state)
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()
            self.back.configure(state="normal" if self.page_index in (1, 2) else "disabled")

    def _submit(self, status, task, success, retry):
        if self.busy or self.closed:
            return
        self.error_frame.grid_remove()
        self.last_retry = retry
        self.status.set(status)
        self._set_busy(True)
        future = self.executor.submit(task)
        # This callback only touches a thread-safe queue; Tk is main-thread only.
        future.add_done_callback(lambda done: self.events.put((done, success)))

    def _poll(self):
        if self.closed:
            return
        try:
            future, success = self.events.get_nowait()
        except Empty:
            pass
        else:
            self._set_busy(False)
            try:
                result = future.result()
            except Exception as error:
                self._handle_failure(error, self.last_retry)
            else:
                success(result)
        self._poll_after = self.window.after(60, self._poll)

    def _handle_failure(self, error, retry):
        if isinstance(error, SetupFailure):
            code = f" · code {error.code}" if error.code is not None else ""
            stage = error.stage.replace("_", " ").capitalize()
            self._failure(f"{stage}{code}", f"{error.message}\n\nWhat to do: {error.action}", retry)
        else:
            self._failure("Setup could not complete this step", f"An unexpected {type(error).__name__} occurred. Your entries have been kept. Copy the diagnostic report so this failure can be investigated.", retry)

    def _failure(self, title, details, retry):
        self.error_title.set(title)
        report = getattr(self.service, "report", None)
        write_error = getattr(report, "write_error", "")
        self.report_location.set(write_error or f"Diagnostic report: {self.service.diagnostic_path}")
        self.error_text.configure(state="normal")
        self.error_text.delete("1.0", "end")
        self.error_text.insert("1.0", details)
        self.error_text.configure(state="disabled")
        self.last_retry = retry
        self.retry_button.configure(state="normal" if retry else "disabled")
        self.error_frame.grid()
        self.status.set("Setup stopped at this step. Your entries are kept; review the message and retry when ready.")
        self.window.after_idle(lambda: self.canvas.yview_moveto(1.0))

    def _retry(self):
        if self.last_retry and not self.busy:
            self.last_retry()

    def _copy_report(self):
        if self.busy:
            self.status.set("Wait for this step to finish, then copy the diagnostic report.")
            return
        try:
            report = self.service.report_text()
            self.window.clipboard_clear()
            self.window.clipboard_append(report)
            self.status.set("Diagnostic report copied. Passwords are not included.")
        except Exception:
            self.status.set(f"Could not copy the report. Diagnostic file: {self.service.diagnostic_path}")

    def _finish(self):
        self.exit_code = 0
        self._close()

    def _close(self):
        if self.busy:
            self.status.set("Setup is still working. Please wait for this step to finish before closing; your database operation is being protected.")
            return
        self.closed = True
        # Secrets are cleared as the view closes; no clipboard operation is implicit.
        self.values["password"].set("")
        self.executor.shutdown(wait=False)
        self.window.after_cancel(self._poll_after)
        self.window.destroy()


def run(root: Path, initial_stage="database") -> int:
    """Open the native wizard; raise WizardUnavailable for a console fallback."""
    if tk is None:
        raise WizardUnavailable("Python's Tcl/Tk component is missing. Install it or use console setup.")
    _windows_dpi()
    try:
        window = tk.Tk()
    except tk.TclError as error:
        raise WizardUnavailable("A graphical desktop is unavailable. Use console setup.") from error
    try:
        from tools.setup_service import SetupService
        wizard = SetupWizard(window, SetupService(Path(root)), initial_stage)
        window.mainloop()
        return wizard.exit_code
    except BaseException:
        try:
            window.destroy()
        except tk.TclError:
            pass
        raise
