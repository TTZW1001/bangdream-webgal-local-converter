from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any


def build_palettes() -> dict[str, dict[str, str]]:
    return {
        "light": {
            "window": "#f5f7f8",
            "panel": "#ffffff",
            "border": "#d8dee4",
            "text": "#17202a",
            "muted": "#59636e",
            "primary": "#256d85",
            "primary_hover": "#1f5b70",
            "secondary": "#eef3f5",
            "secondary_hover": "#e2eaed",
            "input_bg": "#ffffff",
            "output_bg": "#fffdf8",
            "list_bg": "#ffffff",
        },
        "dark": {
            "window": "#162028",
            "panel": "#1d2a33",
            "border": "#30414d",
            "text": "#edf3f7",
            "muted": "#aab8c3",
            "primary": "#3d93ad",
            "primary_hover": "#58a8bf",
            "secondary": "#25343d",
            "secondary_hover": "#30414d",
            "input_bg": "#1c2831",
            "output_bg": "#1a252d",
            "list_bg": "#1d2a33",
        },
    }


def configure_app_theme(app: Any) -> None:
    app.colors = dict(app.palettes[app.theme_var.get()])
    app.root.configure(bg=app.colors["window"])
    app.root.option_add("*Font", app.ui_font)
    style = ttk.Style(app.root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("TFrame", background=app.colors["window"])
    style.configure("Toolbar.TLabel", background=app.colors["window"], foreground=app.colors["muted"], font=app.label_font)
    style.configure("Toolbar.TCheckbutton", background=app.colors["window"], foreground=app.colors["muted"], font=app.small_font)
    style.map("Toolbar.TCheckbutton", background=[("active", app.colors["window"])], foreground=[("active", app.colors["text"])])
    style.configure("PanelTitle.TLabel", background=app.colors["window"], foreground=app.colors["text"], font=app.label_font)
    style.configure("Primary.TButton", font=app.ui_font, padding=(14, 8), foreground="#ffffff", background=app.colors["primary"], borderwidth=0)
    style.map("Primary.TButton", background=[("active", app.colors["primary_hover"]), ("pressed", app.colors["primary_hover"])])
    style.configure("Secondary.TButton", font=app.ui_font, padding=(12, 7), foreground=app.colors["text"], background=app.colors["secondary"], borderwidth=1)
    style.map("Secondary.TButton", background=[("active", app.colors["secondary_hover"]), ("pressed", app.colors["secondary_hover"])])
    style.configure("Quiet.TButton", font=app.small_font, padding=(10, 6), foreground=app.colors["muted"], background=app.colors["window"], borderwidth=1)
    style.map("Quiet.TButton", background=[("active", app.colors["secondary_hover"]), ("pressed", app.colors["secondary_hover"])])
    style.configure("TMenubutton", font=app.ui_font, padding=(10, 7), background=app.colors["secondary"], foreground=app.colors["text"])
    style.configure(
        "App.TCombobox",
        padding=(8, 6),
        arrowsize=14,
        fieldbackground=app.colors["secondary"],
        background=app.colors["secondary"],
        foreground=app.colors["text"],
        bordercolor=app.colors["border"],
        lightcolor=app.colors["border"],
        darkcolor=app.colors["border"],
        arrowcolor=app.colors["text"],
        insertcolor=app.colors["text"],
    )
    style.map(
        "App.TCombobox",
        fieldbackground=[("readonly", app.colors["secondary"]), ("active", app.colors["secondary"])],
        background=[("readonly", app.colors["secondary"]), ("active", app.colors["secondary"])],
        foreground=[("readonly", app.colors["text"]), ("active", app.colors["text"])],
        selectbackground=[("readonly", app.colors["secondary"]), ("active", app.colors["secondary"])],
        selectforeground=[("readonly", app.colors["text"]), ("active", app.colors["text"])],
        arrowcolor=[("readonly", app.colors["text"]), ("active", app.colors["text"])],
        bordercolor=[("focus", app.colors["primary"]), ("!focus", app.colors["border"])],
        lightcolor=[("focus", app.colors["primary"]), ("!focus", app.colors["border"])],
        darkcolor=[("focus", app.colors["primary"]), ("!focus", app.colors["border"])],
    )
    app.root.option_add("*TCombobox*Listbox.background", app.colors["panel"])
    app.root.option_add("*TCombobox*Listbox.foreground", app.colors["text"])
    app.root.option_add("*TCombobox*Listbox.selectBackground", app.colors["primary"])
    app.root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
    app.root.option_add("*TCombobox*Listbox.font", app.ui_font)


def apply_app_theme_to_widgets(app: Any) -> None:
    _apply_theme_recursive(app, app.root)
    app.toolbar.configure(bg=app.colors["window"])
    app.main_pane.configure(bg=app.colors["border"])
    app.top_area.configure(bg=app.colors["window"])
    app.body_shell.configure(bg=app.colors["window"])
    app.body.configure(bg=app.colors["border"])
    app.output_header.configure(bg=app.colors["window"])
    app.correction_area.configure(bg=app.colors["border"])
    app.input_text.configure(bg=app.colors["input_bg"], fg=app.colors["text"], insertbackground=app.colors["primary"])
    app.output_text.configure(bg=app.colors["output_bg"], fg=app.colors["text"], insertbackground=app.colors["primary"])
    app.input_scrollbar.configure(
        command=app.scroll_input_text,
        troughcolor="#d7dee3" if app.theme_var.get() == "light" else "#24343d",
        activebackground=app.colors["primary_hover"],
        bg="#6e8593" if app.theme_var.get() == "light" else "#78b8cc",
        highlightbackground=app.colors["border"],
        highlightcolor=app.colors["border"],
    )
    app.output_scrollbar.configure(
        command=app.scroll_output_text,
        troughcolor="#d7dee3" if app.theme_var.get() == "light" else "#24343d",
        activebackground=app.colors["primary_hover"],
        bg="#6e8593" if app.theme_var.get() == "light" else "#78b8cc",
        highlightbackground=app.colors["border"],
        highlightcolor=app.colors["border"],
    )
    app.pending_list.configure(bg=app.colors["list_bg"], fg=app.colors["text"], selectbackground=app.colors["primary"], selectforeground="#ffffff")
    app.dialogue_list.configure(bg=app.colors["list_bg"], fg=app.colors["text"], selectbackground=app.colors["primary"], selectforeground="#ffffff")
    app.theme_button.configure(text="白天模式" if app.theme_var.get() == "dark" else "黑夜模式")
    app.configure_output_tags()
    app.highlight_output()


def _apply_theme_recursive(app: Any, widget: tk.Misc) -> None:
    for child in widget.winfo_children():
        if isinstance(child, tk.Frame):
            child.configure(bg=app.colors["window"])
        elif isinstance(child, tk.PanedWindow):
            child.configure(bg=app.colors["border"])
        elif isinstance(child, tk.Listbox):
            child.configure(bg=app.colors["list_bg"], fg=app.colors["text"], selectbackground=app.colors["primary"], selectforeground="#ffffff")
        elif isinstance(child, tk.Text):
            bg = app.colors["output_bg"] if child is getattr(app, "output_text", None) else app.colors["input_bg"]
            child.configure(bg=bg, fg=app.colors["text"], insertbackground=app.colors["primary"])
        _apply_theme_recursive(app, child)
