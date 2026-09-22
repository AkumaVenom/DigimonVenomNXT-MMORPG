"""Editable password dialogs with a masked Windows console fallback.

Secrets stay in this process: no command-line argument, shell, log, or temporary
answers file is used for interactive entry. Blank submission and cancellation
are deliberately different outcomes.
"""
from __future__ import annotations

import os
import sys


class PasswordCancelled(KeyboardInterrupt):
    """The operator cancelled instead of submitting a password."""


class GUIUnavailable(RuntimeError):
    """Tk is missing or this session has no graphical desktop."""


def _single_line(value):
    return isinstance(value, str) and not any(ord(c) < 32 or ord(c) == 127 for c in value)


def password_dialog(label):
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError as exc:
        raise GUIUnavailable("Tcl/Tk is not installed.") from exc
    try:
        window = tk.Tk()
    except tk.TclError as exc:
        raise GUIUnavailable("A password window could not open on this desktop.") from exc
    result = [None]
    try:
        window.withdraw()
        window.title("Digimon Venom NXT - Password entry")
        window.resizable(True, False)
        window.minsize(560, 0)
        frame = ttk.Frame(window, padding=22)
        frame.grid(sticky="nsew")
        window.columnconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text="Enter your password", font=("Segoe UI", 15, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
        ttk.Label(frame, text=label, wraplength=570, justify="left").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(0, 10))
        value = tk.StringVar(window)
        revealed = tk.BooleanVar(window, value=False)
        status = tk.StringVar(window, value="Type here or paste. Blank submits the default shown above.")
        entry = ttk.Entry(frame, textvariable=value, show="*", width=52, font=("Segoe UI", 12))
        entry.grid(row=2, column=0, columnspan=3, sticky="ew", ipady=5)
        entry.configure(validate="key", validatecommand=(window.register(_single_line), "%P"))

        def paste(event=None):
            try:
                text = window.clipboard_get()
            except tk.TclError:
                status.set("The clipboard does not contain text.")
                return "break"
            if not _single_line(text):
                status.set("Paste one line without tabs or line breaks. Nothing was pasted.")
                return "break"
            if entry.selection_present():
                entry.delete("sel.first", "sel.last")
            entry.insert("insert", text)
            entry.focus_set()
            return "break"

        def changed(*_):
            status.set(f"{len(value.get())} characters entered. Spaces and punctuation are kept exactly.")

        def accept(event=None):
            text = value.get()
            if not _single_line(text):
                status.set("Use a single-line password without control characters.")
                return "break"
            result[0] = text
            window.quit()
            return "break"

        def cancel(event=None):
            window.quit()
            return "break"

        value.trace_add("write", changed)
        ttk.Checkbutton(frame, text="Show password", variable=revealed,
                        command=lambda: entry.configure(show="" if revealed.get() else "*")).grid(
            row=3, column=0, sticky="w", pady=10)
        ttk.Button(frame, text="Paste", command=paste).grid(row=3, column=1, padx=6)
        ttk.Button(frame, text="Clear", command=lambda: value.set("")).grid(row=3, column=2)
        ttk.Label(frame, textvariable=status, wraplength=570, justify="left").grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(0, 15))
        ttk.Button(frame, text="Cancel setup", command=cancel).grid(row=5, column=1, padx=6)
        ttk.Button(frame, text="Continue", command=accept).grid(row=5, column=2)
        menu = tk.Menu(entry, tearoff=False)
        menu.add_command(label="Paste", command=paste)
        menu.add_command(label="Select all", command=lambda: entry.selection_range(0, "end"))
        entry.bind("<Button-3>", lambda event: menu.tk_popup(event.x_root, event.y_root))
        entry.bind("<<Paste>>", paste)
        window.bind("<Return>", accept)
        window.bind("<Escape>", cancel)
        window.protocol("WM_DELETE_WINDOW", cancel)
        window.update_idletasks()
        window.geometry(f"+{max(0, (window.winfo_screenwidth()-window.winfo_reqwidth())//2)}"
                        f"+{max(0, (window.winfo_screenheight()-window.winfo_reqheight())//2)}")
        window.deiconify()
        window.lift()
        window.after_idle(entry.focus_force)
        window.mainloop()
    finally:
        window.destroy()
    if result[0] is None:
        raise PasswordCancelled("Password entry cancelled.")
    return result[0]


def _windows_clipboard():
    # Access the clipboard only after the operator explicitly presses Ctrl+V.
    import ctypes
    from ctypes import wintypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    if not user32.OpenClipboard(None):
        raise OSError("Clipboard is unavailable.")
    try:
        handle = user32.GetClipboardData(13)  # CF_UNICODETEXT
        pointer = kernel32.GlobalLock(handle) if handle else None
        if not pointer:
            raise OSError("Clipboard has no text.")
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def windows_password(label, read_char=None, output=None, paste=None):
    if read_char is None:
        import msvcrt
        read_char = msvcrt.getwch
    output = output if output is not None else sys.stdout
    paste = paste or _windows_clipboard
    chars = []

    def write(text):
        output.write(text)
        output.flush()

    write(label + "\nTyping shows *; Ctrl+V pastes, Backspace deletes, Ctrl+U clears, Esc cancels.\nPassword: ")
    while True:
        char = read_char()
        if not char:
            raise EOFError("Password input ended before Enter was pressed.")
        if char in ("\r", "\n"):
            write("\n")
            # getwch returns UTF-16 code units for supplementary characters.
            return "".join(chars).encode("utf-16-le", "surrogatepass").decode("utf-16-le")
        if char in ("\x03", "\x1b"):
            write("\n")
            raise PasswordCancelled("Password entry cancelled.")
        if char in ("\x00", "\xe0"):
            read_char()  # Function/navigation keys are not password characters.
        elif char in ("\b", "\x7f"):
            if chars:
                removed = chars.pop()
                write("\b \b")
                if 0xDC00 <= ord(removed) <= 0xDFFF and chars and 0xD800 <= ord(chars[-1]) <= 0xDBFF:
                    chars.pop()
                    write("\b \b")
        elif char == "\x15":
            write("\b \b" * len(chars))
            chars.clear()
        elif char == "\x16":
            try:
                text = paste()
            except Exception:
                write("\a")
                continue
            if not _single_line(text):
                write("\a")
                continue
            chars.extend(text)
            write("*" * len(text))
        elif char.isprintable() or 0xD800 <= ord(char) <= 0xDFFF:
            chars.append(char)
            write("*")


def read_password(label, mode="auto"):
    if mode not in ("auto", "console"):
        raise ValueError("Unknown password input mode.")
    if mode == "auto" and (sys.platform == "win32" or os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        try:
            return password_dialog(label)
        except GUIUnavailable:
            print("Password window unavailable; using console password entry.", file=sys.stderr)
    if not sys.stdin or not sys.stdin.isatty():
        raise RuntimeError("Password entry needs an interactive terminal or desktop. Run the setup BAT directly.")
    if sys.platform == "win32":
        return windows_password(label)
    import getpass
    print("Console password entry: characters are hidden on this terminal. Press Enter when finished.")
    return getpass.getpass(label + ": ")
