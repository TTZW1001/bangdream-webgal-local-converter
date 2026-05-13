from __future__ import annotations

import ctypes
import json
import re
import tkinter as tk
from tkinter import filedialog, font, messagebox, ttk
from pathlib import Path

from .config_loader import load_config
from .converter import convert_text
from .figure_resource_index import scan_figure_directory
from .models import ConversionResult, FigureModelEntry, FigureResourceIndex, SegmentKind
from .ui_dialogs import (
    open_figure_control_settings_dialog,
    open_figure_event_editor_dialog,
    open_figure_mapping_dialog,
    open_figure_resource_settings_dialog,
    open_model_settings_dialog,
    open_scene_lock_settings_dialog,
    open_speaker_picker_dialog,
)
from .ui_theme import apply_app_theme_to_widgets, build_palettes, configure_app_theme


class TkMainWindow:
    TOP_PANE_MIN_WIDTH = 420
    BOTTOM_PANE_MIN_WIDTH = 320

    def __init__(self, root: tk.Tk, config_dir: Path) -> None:
        self.root = root
        self.config_dir = config_dir
        self.settings_path = config_dir.parent / "app_settings.json"
        self.settings = self._load_settings()
        self.config = load_config(config_dir)
        self.model_overrides: dict[str, str] = {}
        self.speaker_overrides: dict[int, str] = {}
        self.segment_scene_locks: dict[int, str] = {}
        self.figure_controls: dict[str, dict[str, str]] = {}
        self.figure_event_overrides: dict[int, dict[str, str]] = {}
        self.figure_source_mode = self._load_figure_source_mode()
        self.figure_root_dir: Path | None = None
        self.figure_resource_index: FigureResourceIndex | None = None
        self.figure_character_mappings: dict[str, str] = {}
        self.output_figure_events: dict[int, tuple[int, str]] = {}
        self.last_result: ConversionResult | None = None
        self.pending_segment_orders: list[int | None] = []
        self.dialogue_segment_orders: list[int] = []
        self.output_segment_line_map: dict[int, int] = {}
        self._syncing_text_scroll = False
        self._scroll_target = "input"
        self.link_scroll_var = tk.BooleanVar(value=True)
        self.input_segment_lines: list[int] = []
        self.output_segment_lines: list[int] = []
        root.title("邦邦WebGAL转化器")
        root.geometry("1160x680")
        root.minsize(1120, 620)

        self.palettes = build_palettes()
        self.theme_var = tk.StringVar(value=self._load_theme_preference())
        self.colors = dict(self.palettes[self.theme_var.get()])
        self.ui_font = font.Font(family="Microsoft YaHei UI", size=11)
        self.label_font = font.Font(family="Microsoft YaHei UI", size=11, weight="bold")
        self.text_font = font.Font(family="Microsoft YaHei UI", size=12)
        self.script_font = font.Font(family="Microsoft YaHei UI", size=12)
        self.dialogue_font = font.Font(family="Microsoft YaHei UI", size=12, weight="bold")
        self.small_font = font.Font(family="Microsoft YaHei UI", size=10)
        self.configure_theme()

        self.toolbar = tk.Frame(root, bg=self.colors["window"])
        self.toolbar.pack(fill=tk.X, padx=12, pady=(10, 8))

        ttk.Button(self.toolbar, text="导入文本", command=self.import_text, style="Secondary.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(self.toolbar, text="清空文本", command=self.clear_texts, style="Quiet.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(self.toolbar, text="生成脚本", command=self.generate_script, style="Primary.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(self.toolbar, text="导出脚本", command=self.export_script, style="Secondary.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(self.toolbar, text="模型设置", command=self.open_model_settings, style="Secondary.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(self.toolbar, text="立绘资源设置", command=self.open_figure_resource_settings, style="Secondary.TButton").pack(side=tk.LEFT, padx=(0, 8))
        self.theme_button = ttk.Button(self.toolbar, text="黑夜模式", command=self.toggle_theme, style="Quiet.TButton")
        self.theme_button.pack(side=tk.RIGHT)
        ttk.Label(self.toolbar, text="模型模式", style="Toolbar.TLabel").pack(side=tk.LEFT, padx=(18, 6))
        self.mode_var = tk.StringVar(value="auto")
        mode_menu = self._make_combobox(self.toolbar, self.mode_var, ("auto", "31", "generic"), width=8)
        mode_menu.pack(side=tk.LEFT)
        ttk.Label(self.toolbar, text="默认学校", style="Toolbar.TLabel").pack(side=tk.LEFT, padx=(18, 6))
        self.school_var = tk.StringVar(value="auto")
        school_menu = self._make_combobox(self.toolbar, self.school_var, ("auto", "花咲川", "羽丘", "月之森"), width=8)
        school_menu.pack(side=tk.LEFT)
        self.scene_lock_var = tk.StringVar(value="")

        self.figure_status_var = tk.StringVar(value="")
        self.figure_status_label = ttk.Label(root, textvariable=self.figure_status_var, style="Toolbar.TLabel")
        self.figure_status_label.pack(fill=tk.X, padx=12, pady=(0, 6))

        self.main_pane = tk.PanedWindow(root, orient=tk.VERTICAL, sashrelief=tk.RAISED, bg=self.colors["border"], sashwidth=6)
        self.main_pane.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 10))

        self.top_area = tk.Frame(self.main_pane, bg=self.colors["window"])
        self.correction_area = tk.PanedWindow(self.main_pane, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, bg=self.colors["border"], sashwidth=6)
        self.main_pane.add(self.top_area, stretch="always")
        self.main_pane.add(self.correction_area, minsize=180)

        self.body_shell = tk.Frame(self.top_area, bg=self.colors["window"])
        self.body_shell.pack(fill=tk.BOTH, expand=True)

        self.body = tk.PanedWindow(self.body_shell, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, bg=self.colors["border"], sashwidth=6)
        self.body.pack(fill=tk.BOTH, expand=True)

        left = tk.Frame(self.body, bg=self.colors["window"])
        right = tk.Frame(self.body, bg=self.colors["window"])
        self.body.add(left, minsize=self.TOP_PANE_MIN_WIDTH, stretch="always")
        self.body.add(right, minsize=self.TOP_PANE_MIN_WIDTH, stretch="always")

        ttk.Label(left, text="原文", style="PanelTitle.TLabel").pack(fill=tk.X, pady=(0, 4))
        input_shell = tk.Frame(left, bg=self.colors["window"])
        input_shell.pack(fill=tk.BOTH, expand=True)
        input_shell.grid_columnconfigure(0, weight=1)
        input_shell.grid_rowconfigure(0, weight=1)
        self.input_text = tk.Text(input_shell, wrap=tk.WORD, undo=True, font=self.text_font, bg=self.colors["input_bg"], fg=self.colors["text"], relief=tk.SOLID, bd=1, padx=10, pady=10, insertbackground=self.colors["primary"], spacing1=2, spacing3=2)
        self.input_text.configure(yscrollcommand=lambda first, last: self.on_text_yscroll("input", first, last))
        self.input_text.grid(row=0, column=0, sticky="nsew")
        self.input_scrollbar = tk.Scrollbar(
            input_shell,
            orient=tk.VERTICAL,
            command=self.scroll_input_text,
            width=18,
            bd=1,
            relief=tk.RAISED,
            troughcolor="#d7dee3" if self.theme_var.get() == "light" else "#24343d",
            activebackground=self.colors["primary_hover"],
            bg="#6e8593" if self.theme_var.get() == "light" else "#78b8cc",
            highlightthickness=1,
            highlightbackground=self.colors["border"],
            highlightcolor=self.colors["border"],
        )
        self.input_scrollbar.grid(row=0, column=1, sticky="ns", padx=(8, 2))
        self.input_text.bind("<Enter>", lambda _event: self.set_scroll_target("input"))
        self.input_text.bind("<FocusIn>", lambda _event: self.set_scroll_target("input"))
        self.input_text.bind("<MouseWheel>", lambda event: self.on_mousewheel("input", event))

        self.output_header = tk.Frame(right, bg=self.colors["window"])
        self.output_header.pack(fill=tk.X)
        ttk.Label(self.output_header, text="生成结果", style="PanelTitle.TLabel").pack(side=tk.LEFT, pady=(0, 4))
        ttk.Checkbutton(
            self.output_header,
            text="联动滚动",
            variable=self.link_scroll_var,
            command=self.on_toggle_link_scroll,
            style="Toolbar.TCheckbutton",
        ).pack(side=tk.RIGHT, padx=(10, 0), pady=(0, 4))
        ttk.Button(self.output_header, text="复制", command=self.copy_output_script, style="Secondary.TButton").pack(side=tk.RIGHT, padx=(6, 0), pady=(0, 4))
        ttk.Button(self.output_header, text="所选行改对白", command=self.correct_selected_output_line, style="Secondary.TButton").pack(side=tk.RIGHT, padx=(6, 0), pady=(0, 4))
        ttk.Button(self.output_header, text="微调所选立绘行", command=self.edit_selected_figure_event, style="Secondary.TButton").pack(side=tk.RIGHT, padx=(6, 0), pady=(0, 4))
        ttk.Button(self.output_header, text="清空立绘微调", command=self.clear_figure_event_overrides, style="Quiet.TButton").pack(side=tk.RIGHT, pady=(0, 4))
        output_shell = tk.Frame(right, bg=self.colors["window"])
        output_shell.pack(fill=tk.BOTH, expand=True)
        output_shell.grid_columnconfigure(0, weight=1)
        output_shell.grid_rowconfigure(0, weight=1)
        self.output_text = tk.Text(output_shell, wrap=tk.WORD, undo=True, font=self.script_font, bg=self.colors["output_bg"], fg=self.colors["text"], relief=tk.SOLID, bd=1, padx=10, pady=10, insertbackground=self.colors["primary"], spacing1=2, spacing3=2)
        self.output_text.configure(yscrollcommand=lambda first, last: self.on_text_yscroll("output", first, last))
        self.output_text.grid(row=0, column=0, sticky="nsew")
        self.output_scrollbar = tk.Scrollbar(
            output_shell,
            orient=tk.VERTICAL,
            command=self.scroll_output_text,
            width=18,
            bd=1,
            relief=tk.RAISED,
            troughcolor="#d7dee3" if self.theme_var.get() == "light" else "#24343d",
            activebackground=self.colors["primary_hover"],
            bg="#6e8593" if self.theme_var.get() == "light" else "#78b8cc",
            highlightthickness=1,
            highlightbackground=self.colors["border"],
            highlightcolor=self.colors["border"],
        )
        self.output_scrollbar.grid(row=0, column=1, sticky="ns", padx=(8, 2))
        self.output_text.bind("<Enter>", lambda _event: self.set_scroll_target("output"))
        self.output_text.bind("<FocusIn>", lambda _event: self.set_scroll_target("output"))
        self.output_text.bind("<MouseWheel>", lambda event: self.on_mousewheel("output", event))
        self.configure_output_tags()
        self.output_text.bind("<Double-Button-1>", self.open_figure_event_editor)

        pending_frame = tk.Frame(self.correction_area, bg=self.colors["window"])
        dialogue_frame = tk.Frame(self.correction_area, bg=self.colors["window"])
        self.correction_area.add(pending_frame, minsize=self.BOTTOM_PANE_MIN_WIDTH, stretch="always")
        self.correction_area.add(dialogue_frame, minsize=self.BOTTOM_PANE_MIN_WIDTH, stretch="always")

        ttk.Label(pending_frame, text="待确认项", style="PanelTitle.TLabel").pack(fill=tk.X, pady=(0, 4))
        self.pending_list = tk.Listbox(pending_frame, height=8, font=self.ui_font, bg=self.colors["list_bg"], fg=self.colors["text"], relief=tk.SOLID, bd=1, activestyle="none")
        self.pending_list.pack(fill=tk.BOTH, expand=True)
        pending_buttons = tk.Frame(pending_frame, bg=self.colors["window"])
        pending_buttons.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(pending_buttons, text="指定说话人", command=self.correct_selected_pending, style="Secondary.TButton").pack(side=tk.LEFT)
        ttk.Button(pending_buttons, text="标记为旁白", command=self.mark_selected_pending_as_narration, style="Quiet.TButton").pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(dialogue_frame, text="对白修正", style="PanelTitle.TLabel").pack(fill=tk.X, pady=(0, 4))
        self.dialogue_list = tk.Listbox(dialogue_frame, height=8, font=self.ui_font, bg=self.colors["list_bg"], fg=self.colors["text"], relief=tk.SOLID, bd=1, activestyle="none")
        self.dialogue_list.pack(fill=tk.BOTH, expand=True)
        dialogue_buttons = tk.Frame(dialogue_frame, bg=self.colors["window"])
        dialogue_buttons.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(dialogue_buttons, text="指定说话人", command=self.correct_selected_dialogue, style="Secondary.TButton").pack(side=tk.LEFT)
        ttk.Button(dialogue_buttons, text="标记为旁白", command=self.mark_selected_dialogue_as_narration, style="Quiet.TButton").pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(dialogue_buttons, text="清空人工修正", command=self.clear_speaker_overrides, style="Quiet.TButton").pack(side=tk.LEFT, padx=(8, 0))

        self.pending_list.bind("<Double-Button-1>", lambda _event: self.correct_selected_pending())
        self.dialogue_list.bind("<Double-Button-1>", lambda _event: self.correct_selected_dialogue())
        self.body.bind("<Configure>", self.on_body_configure)
        self.correction_area.bind("<Configure>", self.on_correction_area_configure)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._restore_figure_directory()
        self.refresh_figure_status()
        self.root.after(120, self.set_initial_layout)

    def _load_settings(self) -> dict:
        try:
            if self.settings_path.exists():
                payload = json.loads(self.settings_path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    return payload
        except (OSError, json.JSONDecodeError):
            pass
        return {}

    def _load_theme_preference(self) -> str:
        theme = self.settings.get("theme")
        if theme in {"light", "dark"}:
            return theme
        return "light"

    def _load_figure_source_mode(self) -> str:
        value = str(self.settings.get("figure_source_mode") or "builtin").strip()
        return value if value in {"builtin", "custom"} else "builtin"

    def _save_settings(self) -> None:
        try:
            payload = dict(self.settings)
            payload["theme"] = self.theme_var.get()
            payload["figure_source_mode"] = self.figure_source_mode
            payload["figure_root_dir"] = str(self.figure_root_dir) if self.figure_root_dir else ""
            mapping_store = dict(payload.get("figure_character_mappings", {}))
            current_key = self._figure_root_settings_key()
            if current_key:
                mapping_store[current_key] = dict(self.figure_character_mappings)
            payload["figure_character_mappings"] = mapping_store
            self.settings_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def configure_theme(self) -> None:
        configure_app_theme(self)

    def set_initial_layout(self) -> None:
        try:
            total_height = self.main_pane.winfo_height()
            total_width = self.body.winfo_width()
            if total_height > 0:
                self.main_pane.sash_place(0, 0, int(total_height * 0.72))
            if total_width > 0:
                self.body.sash_place(0, self._clamp_pane_sash(total_width, total_width * 0.5, self.TOP_PANE_MIN_WIDTH), 0)
                bottom_width = self.correction_area.winfo_width()
                if bottom_width > 0:
                    self.correction_area.sash_place(0, self._clamp_pane_sash(bottom_width, bottom_width * 0.5, self.BOTTOM_PANE_MIN_WIDTH), 0)
        except tk.TclError:
            return

    def _clamp_pane_sash(self, total_width: int, desired: float, pane_min_width: int) -> int:
        min_x = pane_min_width
        max_x = max(min_x, total_width - pane_min_width)
        return int(max(min_x, min(max_x, desired)))

    def on_body_configure(self, _event: tk.Event[tk.Misc]) -> None:
        try:
            total_width = self.body.winfo_width()
            if total_width <= 0:
                return
            sash_x = self.body.sash_coord(0)[0]
            clamped = self._clamp_pane_sash(total_width, sash_x, self.TOP_PANE_MIN_WIDTH)
            if clamped != sash_x:
                self.body.sash_place(0, clamped, 0)
        except tk.TclError:
            return

    def on_correction_area_configure(self, _event: tk.Event[tk.Misc]) -> None:
        try:
            total_width = self.correction_area.winfo_width()
            if total_width <= 0:
                return
            sash_x = self.correction_area.sash_coord(0)[0]
            clamped = self._clamp_pane_sash(total_width, sash_x, self.BOTTOM_PANE_MIN_WIDTH)
            if clamped != sash_x:
                self.correction_area.sash_place(0, clamped, 0)
        except tk.TclError:
            return

    def toggle_theme(self) -> None:
        self.theme_var.set("dark" if self.theme_var.get() == "light" else "light")
        self.configure_theme()
        self.apply_theme_to_widgets()
        self._save_settings()

    def on_close(self) -> None:
        self._save_settings()
        self.root.destroy()

    def apply_theme_to_widgets(self) -> None:
        apply_app_theme_to_widgets(self)

    def _make_combobox(self, parent: tk.Misc, variable: tk.StringVar, values: list[str] | tuple[str, ...], width: int | None = None) -> ttk.Combobox:
        combo = ttk.Combobox(parent, textvariable=variable, values=list(values), state="readonly", style="App.TCombobox")
        if width is not None:
            combo.configure(width=width)
        return combo

    def on_text_yscroll(self, source: str, first: str, last: str) -> None:
        if source == "input":
            self.input_scrollbar.set(first, last)
        else:
            self.output_scrollbar.set(first, last)

    def _scroll_linked_source(self, source: str, *args: str) -> None:
        self._syncing_text_scroll = True
        try:
            source_widget = self.input_text if source == "input" else self.output_text
            if self.link_scroll_var.get():
                source_widget.yview(*args)
                other_name = "output" if source == "input" else "input"
                if not self.sync_other_text_to_segment(source, other_name):
                    other_widget = self.output_text if source == "input" else self.input_text
                    other_widget.yview_moveto(source_widget.yview()[0])
            else:
                source_widget.yview(*args)
        finally:
            self._syncing_text_scroll = False

    def scroll_input_text(self, *args: str) -> None:
        self.set_scroll_target("input")
        if self.link_scroll_var.get():
            self._scroll_linked_source("input", *args)
            return
        self.input_text.yview(*args)

    def scroll_output_text(self, *args: str) -> None:
        self.set_scroll_target("output")
        if self.link_scroll_var.get():
            self._scroll_linked_source("output", *args)
            return
        self.output_text.yview(*args)

    def set_scroll_target(self, target: str) -> None:
        self._scroll_target = target

    def on_toggle_link_scroll(self) -> None:
        if not self.link_scroll_var.get():
            return
        source = self._scroll_target if self._scroll_target in {"input", "output"} else "input"
        source_widget = self.input_text if source == "input" else self.output_text
        other_name = "output" if source == "input" else "input"
        if not self.sync_other_text_to_segment(source, other_name):
            other_widget = self.output_text if source == "input" else self.input_text
            other_widget.yview_moveto(source_widget.yview()[0])

    def on_mousewheel(self, source: str, event: tk.Event[tk.Text]) -> str:
        self.set_scroll_target(source)
        delta = 0
        if getattr(event, "delta", 0):
            delta = -1 if event.delta > 0 else 1
        if delta == 0:
            return "break"
        self._syncing_text_scroll = True
        try:
            source_widget = self.input_text if source == "input" else self.output_text
            if self.link_scroll_var.get():
                source_widget.yview_scroll(delta, "units")
                other_name = "output" if source == "input" else "input"
                if not self.sync_other_text_to_segment(source, other_name):
                    other_widget = self.output_text if source == "input" else self.input_text
                    other_widget.yview_moveto(source_widget.yview()[0])
            else:
                source_widget.yview_scroll(delta, "units")
        finally:
            self._syncing_text_scroll = False
        return "break"

    def sync_other_text_to_segment(self, source: str, target: str) -> bool:
        if not self.last_result:
            return False
        source_widget = self.input_text if source == "input" else self.output_text
        target_widget = self.output_text if target == "output" else self.input_text
        source_lines = self.input_segment_lines if source == "input" else self.output_segment_lines
        target_lines = self.output_segment_lines if source == "input" else self.input_segment_lines
        if not source_lines or not target_lines:
            return False
        visible_line = int(source_widget.index("@0,0").split(".", 1)[0])
        segment_index = 0
        for idx, line_number in enumerate(source_lines):
            if line_number <= visible_line:
                segment_index = idx
            else:
                break
        segment_index = max(0, min(segment_index, len(target_lines) - 1))
        target_line = target_lines[segment_index]
        total_lines = max(int(target_widget.index("end-1c").split(".", 1)[0]), 1)
        target_widget.yview_moveto(max(0.0, min(1.0, (target_line - 1) / total_lines)))
        return True

    def rebuild_scroll_sync_maps(self) -> None:
        self.input_segment_lines.clear()
        self.output_segment_lines.clear()
        self.output_segment_line_map.clear()
        if not self.last_result:
            return
        search_from = "1.0"
        for segment in self.last_result.segments:
            index = self.input_text.search(segment.raw, search_from, stopindex=tk.END)
            if not index:
                continue
            self.input_segment_lines.append(int(index.split(".", 1)[0]))
            search_from = f"{index}+{max(len(segment.raw), 1)}c"
        segment_order = 0
        for line_number, line in enumerate(self.output_text.get("1.0", tk.END).splitlines(), start=1):
            if line.startswith("changeBg:") or line.startswith("changeFigure:"):
                continue
            if line.startswith(":") or ":" in line:
                self.output_segment_lines.append(line_number)
                self.output_segment_line_map[segment_order] = line_number
                segment_order += 1
        expected = min(len(self.input_segment_lines), len(self.output_segment_lines), len(self.last_result.segments))
        self.input_segment_lines = self.input_segment_lines[:expected]
        self.output_segment_lines = self.output_segment_lines[:expected]
        self.output_segment_line_map = {
            segment_order: line_number
            for segment_order, line_number in self.output_segment_line_map.items()
            if segment_order < expected
        }

    def import_text(self) -> None:
        path = filedialog.askopenfilename(
            title="导入文本",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
        )
        if not path:
            return
        try:
            content = Path(path).read_text(encoding="utf-8-sig")
        except OSError as exc:
            messagebox.showerror("导入失败", str(exc))
            return
        self.input_text.delete("1.0", tk.END)
        self.input_text.insert("1.0", content)
        self.speaker_overrides.clear()
        self.segment_scene_locks.clear()

    def clear_texts(self) -> None:
        self.input_text.delete("1.0", tk.END)
        self.output_text.delete("1.0", tk.END)
        self.pending_list.delete(0, tk.END)
        self.dialogue_list.delete(0, tk.END)
        self.speaker_overrides.clear()
        self.segment_scene_locks.clear()
        self.figure_event_overrides.clear()
        self.output_figure_events.clear()
        self.last_result = None
        self.pending_segment_orders.clear()
        self.dialogue_segment_orders.clear()
        self.output_segment_line_map.clear()
        self.input_segment_lines.clear()
        self.output_segment_lines.clear()

    def select_figure_directory(self) -> None:
        selected = filedialog.askdirectory(title="选择 figure 根目录")
        if not selected:
            return
        self._apply_figure_directory(Path(selected))

    def _restore_figure_directory(self) -> None:
        raw_path = str(self.settings.get("figure_root_dir") or "").strip()
        if not raw_path or self.figure_source_mode != "custom":
            return
        figure_dir = Path(raw_path)
        if figure_dir.exists() and figure_dir.is_dir():
            self._apply_figure_directory(figure_dir, show_message=False)

    def _apply_figure_directory(self, figure_dir: Path, show_message: bool = True) -> None:
        self.figure_root_dir = figure_dir
        self.figure_character_mappings = self._load_figure_character_mappings(figure_dir)
        index = scan_figure_directory(
            figure_dir,
            self.config,
            manual_mappings=self.figure_character_mappings,
        )
        self.figure_resource_index = index
        self.settings["figure_root_dir"] = str(figure_dir)
        self._save_settings()
        self.refresh_figure_status()
        if show_message:
            messagebox.showinfo("Figure 扫描完成", self._build_figure_scan_summary(index))

    def _figure_root_settings_key(self, figure_dir: Path | None = None) -> str | None:
        target = figure_dir or self.figure_root_dir
        if not target:
            return None
        return str(target)

    def _load_figure_character_mappings(self, figure_dir: Path) -> dict[str, str]:
        raw_store = self.settings.get("figure_character_mappings", {})
        if not isinstance(raw_store, dict):
            return {}
        raw_mapping = raw_store.get(self._figure_root_settings_key(figure_dir), {})
        if not isinstance(raw_mapping, dict):
            return {}
        return {
            str(source_name): str(character_id)
            for source_name, character_id in raw_mapping.items()
            if str(character_id).strip()
        }

    def _build_figure_scan_summary(self, index: FigureResourceIndex) -> str:
        lines = [
            f"目录：{index.root_dir}",
            index.summary_text(),
        ]
        if index.unmapped_characters:
            preview = "、".join(index.unmapped_characters[:8])
            suffix = " ……" if len(index.unmapped_characters) > 8 else ""
            lines.append(f"未映射角色：{preview}{suffix}")
        return "\n".join(lines)

    def refresh_figure_status(self) -> None:
        if self.figure_source_mode == "builtin":
            self.figure_status_var.set("立绘资源：系统默认内置")
            return
        if self.figure_root_dir and self.figure_resource_index:
            self.figure_status_var.set(
                f"立绘资源：自定义目录 {self.figure_root_dir.name} | {self.figure_resource_index.summary_text()}"
            )
            return
        if self.figure_root_dir:
            self.figure_status_var.set(f"立绘资源：自定义目录 {self.figure_root_dir.name} | 尚未完成扫描")
            return
        self.figure_status_var.set("立绘资源：自定义目录（未选择）")

    def open_figure_mapping_settings(self) -> None:
        if self.figure_source_mode != "custom":
            messagebox.showinfo("当前为内置资源", "请先在立绘资源设置里切换到“自定义 figure 目录”。")
            return
        if not self.figure_root_dir or not self.figure_resource_index:
            messagebox.showinfo("未选择目录", "请先选择外部 Figure 目录。")
            return
        open_figure_mapping_dialog(self)

    def apply_figure_character_mappings(self, mapping_values: dict[str, str]) -> None:
        self.figure_character_mappings = {
            str(source_name): str(character_id)
            for source_name, character_id in mapping_values.items()
            if str(character_id).strip()
        }
        if not self.figure_root_dir:
            return
        self._apply_figure_directory(self.figure_root_dir, show_message=False)

    def open_figure_resource_settings(self) -> None:
        open_figure_resource_settings_dialog(self)

    def apply_figure_resource_settings(self, source_mode: str, figure_dir: Path | None) -> None:
        self.figure_source_mode = source_mode if source_mode in {"builtin", "custom"} else "builtin"
        if self.figure_source_mode == "builtin":
            self.figure_resource_index = None
            self.figure_character_mappings = {}
            self.refresh_figure_status()
            self._save_settings()
            return
        if figure_dir and figure_dir.exists() and figure_dir.is_dir():
            self._apply_figure_directory(figure_dir, show_message=False)
            return
        self.figure_root_dir = figure_dir
        self.figure_resource_index = None
        self.refresh_figure_status()
        self._save_settings()

    def external_figure_models_for(self, character_id: str) -> dict[str, FigureModelEntry]:
        if not self.figure_resource_index:
            return {}
        return self.figure_resource_index.models_for_character_id(character_id)

    def copy_output_script(self) -> None:
        script = self.output_text.get("1.0", tk.END).strip()
        if not script:
            messagebox.showinfo("没有可复制内容", "请先生成脚本。")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(script)
        self.root.update()

    def generate_script(self) -> None:
        source = self.input_text.get("1.0", tk.END).strip()
        try:
            result = convert_text(
                source,
                self.config_dir,
                resource_mode=self.mode_var.get(),
                model_overrides=self.model_overrides,
                scene_school=self.school_var.get(),
                speaker_overrides=self.speaker_overrides,
                scene_lock=self.scene_lock_var.get().strip() or None,
                segment_scene_locks=self.segment_scene_locks,
                figure_controls=self.figure_controls,
                figure_event_overrides=self.figure_event_overrides,
                figure_resource_index=self.figure_resource_index if self.figure_source_mode == "custom" else None,
            )
        except Exception as exc:  # pragma: no cover - GUI safety net
            messagebox.showerror("生成失败", str(exc))
            return

        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", result.script)
        self.last_result = result
        self.index_output_figure_events(result.script)
        self.rebuild_scroll_sync_maps()
        self.refresh_correction_lists(result)
        self.highlight_output()

    def index_output_figure_events(self, script: str) -> None:
        self.output_figure_events.clear()
        event_index = 0
        for line_number, line in enumerate(script.splitlines(), start=1):
            if not line.startswith("changeFigure:") or line.startswith("changeFigure: -id="):
                continue
            match = re.search(r"-id=([^\s;]+)", line)
            if not match:
                continue
            self.output_figure_events[line_number] = (event_index, match.group(1))
            event_index += 1

    def configure_output_tags(self) -> None:
        if self.theme_var.get() == "dark":
            bg_line = "#79c0ff"
            figure_fg = "#ffbe7a"
            figure_bg = "#2a2219"
            figure_override_bg = "#3a2a17"
            narration = "#aab8c3"
            dialogue = "#edf3f7"
            dialogue_bg = "#22313a"
            custom = "#d29eff"
            warning = "#ff7b8a"
            pending_bg = "#40232a"
        else:
            bg_line = "#165d9f"
            figure_fg = "#8a4b00"
            figure_bg = "#fff7e6"
            figure_override_bg = "#ffe4b8"
            narration = "#555555"
            dialogue = "#111111"
            dialogue_bg = "#f1f7fb"
            custom = "#7a2f8f"
            warning = "#b00020"
            pending_bg = "#fff0f3"
        self.output_text.tag_configure("bg_line", foreground=bg_line)
        self.output_text.tag_configure("figure_line", foreground=figure_fg, background=figure_bg)
        self.output_text.tag_configure("figure_override_line", foreground=figure_fg, background=figure_override_bg)
        self.output_text.tag_configure("narration_line", foreground=narration)
        self.output_text.tag_configure("dialogue_line", foreground=dialogue, background=dialogue_bg, font=self.dialogue_font)
        self.output_text.tag_configure("custom_line", foreground=custom)
        self.output_text.tag_configure("warning_line", foreground=warning)
        self.output_text.tag_configure("pending_line", underline=True, background=pending_bg)

    def highlight_output(self) -> None:
        for tag in ("bg_line", "figure_line", "figure_override_line", "narration_line", "dialogue_line", "custom_line", "warning_line", "pending_line"):
            self.output_text.tag_remove(tag, "1.0", tk.END)
        lines = self.output_text.get("1.0", tk.END).splitlines()
        figure_event_index = 0
        for line_number, line in enumerate(lines, start=1):
            tag = "dialogue_line"
            if line.startswith("changeBg:"):
                tag = "bg_line"
            elif line.startswith("changeFigure:"):
                tag = "figure_line"
                if not line.startswith("changeFigure: -id="):
                    if figure_event_index in self.figure_event_overrides:
                        tag = "figure_override_line"
                    figure_event_index += 1
            elif line.startswith(":"):
                tag = "narration_line"
            elif line.startswith("未知:") or line.startswith("; TODO"):
                tag = "warning_line"
            elif " -figureId=" not in line and ":" in line:
                tag = "custom_line"
            self.output_text.tag_add(tag, f"{line_number}.0", f"{line_number}.end")
        for segment_order in {order for order in self.pending_segment_orders if order is not None}:
            line_number = self.output_segment_line_map.get(segment_order)
            if line_number:
                self.output_text.tag_add("pending_line", f"{line_number}.0", f"{line_number}.end")

    def refresh_correction_lists(self, result: ConversionResult) -> None:
        self.pending_list.delete(0, tk.END)
        self.pending_segment_orders.clear()
        for item in result.pending_items:
            self.pending_segment_orders.append(item.segment_index)
            self.pending_list.insert(
                tk.END,
                f"#{item.index} {item.issue_type}: {item.raw} | {item.suggestion}",
            )
        self.dialogue_list.delete(0, tk.END)
        self.dialogue_segment_orders.clear()
        for segment_order, segment in enumerate(result.segments):
            if segment.kind != SegmentKind.DIALOGUE:
                continue
            self.dialogue_segment_orders.append(segment_order)
            override = self.speaker_overrides.get(segment_order)
            speaker = self._override_display_name(override) or segment.speaker_name or segment.speaker_hint or "未知"
            overridden = " *" if segment_order in self.speaker_overrides else ""
            self.dialogue_list.insert(tk.END, f"#{segment_order}{overridden} {speaker}: {segment.text}")

    def _override_display_name(self, override: str | None) -> str | None:
        if not override:
            return None
        if override.startswith("name:"):
            return override[5:].strip() or None
        if override == "kind:narration":
            return "旁白"
        if override.startswith("char:"):
            character_id = override[5:].strip()
            character = self.config.characters.get(character_id)
            return character.display_name if character else character_id
        character = self.config.characters.get(override)
        return character.display_name if character else override

    def correct_selected_pending(self) -> None:
        selection = self.pending_list.curselection()
        if not selection:
            return
        segment_order = self.pending_segment_orders[selection[0]]
        if segment_order is None:
            messagebox.showinfo("无法修正", "这个待确认项没有可定位的对白片段。")
            return
        self.open_speaker_picker(segment_order)

    def correct_selected_dialogue(self) -> None:
        selection = self.dialogue_list.curselection()
        if not selection:
            return
        self.open_speaker_picker(self.dialogue_segment_orders[selection[0]])

    def mark_selected_pending_as_narration(self) -> None:
        selection = self.pending_list.curselection()
        if not selection:
            return
        segment_order = self.pending_segment_orders[selection[0]]
        if segment_order is None:
            messagebox.showinfo("无法修正", "这个待确认项没有可定位的对白片段。")
            return
        self.speaker_overrides[segment_order] = "kind:narration"
        self.generate_script()

    def mark_selected_dialogue_as_narration(self) -> None:
        selection = self.dialogue_list.curselection()
        if not selection:
            return
        self.speaker_overrides[self.dialogue_segment_orders[selection[0]]] = "kind:narration"
        self.generate_script()

    def open_speaker_picker(self, segment_order: int) -> None:
        open_speaker_picker_dialog(self, segment_order)

    def clear_speaker_overrides(self) -> None:
        if not self.speaker_overrides:
            return
        self.speaker_overrides.clear()
        self.generate_script()

    def edit_selected_figure_event(self) -> None:
        index = self.output_text.index(tk.INSERT)
        line_number = int(index.split(".", 1)[0])
        self.open_figure_event_editor_for_line(line_number)

    def correct_selected_output_line(self) -> None:
        index = self.output_text.index(tk.INSERT)
        line_number = int(index.split(".", 1)[0])
        segment_order = self.find_segment_order_for_output_line(line_number)
        if segment_order is None:
            messagebox.showinfo("无法修正", "请选择一行对白或旁白脚本内容。")
            return
        self.open_speaker_picker(segment_order)

    def clear_figure_event_overrides(self) -> None:
        if not self.figure_event_overrides:
            return
        self.figure_event_overrides.clear()
        self.generate_script()

    def open_figure_event_editor(self, event: tk.Event[tk.Text]) -> None:
        index = self.output_text.index(f"@{event.x},{event.y}")
        line_number = int(index.split(".", 1)[0])
        if line_number in self.output_figure_events:
            self.open_figure_event_editor_for_line(line_number)
            return
        segment_order = self.find_segment_order_for_output_line(line_number)
        if segment_order is not None:
            self.open_speaker_picker(segment_order)

    def open_figure_event_editor_for_line(self, line_number: int) -> None:
        open_figure_event_editor_dialog(self, line_number)

    def find_segment_order_for_output_line(self, line_number: int) -> int | None:
        for segment_order, mapped_line in self.output_segment_line_map.items():
            if mapped_line == line_number:
                return segment_order
        return None

    def open_scene_lock_settings(self) -> None:
        open_scene_lock_settings_dialog(self)

    def open_figure_control_settings(self) -> None:
        open_figure_control_settings_dialog(self)

    def open_model_settings(self) -> None:
        open_model_settings_dialog(self)

    def export_script(self) -> None:
        path = filedialog.asksaveasfilename(
            title="导出脚本",
            defaultextension=".txt",
            initialfile="scene.txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
        )
        if not path:
            return
        try:
            Path(path).write_text(self.output_text.get("1.0", tk.END), encoding="utf-8", newline="\n")
        except OSError as exc:
            messagebox.showerror("导出失败", str(exc))


def main(config_dir: Path) -> int:  # pragma: no cover - GUI entry point
    root = tk.Tk()
    project_root = config_dir.parent
    _apply_app_icon(root, project_root)
    TkMainWindow(root, config_dir)
    root.mainloop()
    return 0


def _apply_app_icon(root: tk.Tk, project_root: Path) -> None:
    icon_ico = project_root / "icon.ico"
    icon_png = project_root / "icon.png"
    try:
        if icon_ico.exists():
            root.iconbitmap(default=str(icon_ico))
        if icon_png.exists():
            icon_image = tk.PhotoImage(file=str(icon_png))
            root.iconphoto(True, icon_image)
            root._app_icon_image = icon_image  # type: ignore[attr-defined]
        legacy_ico = project_root / "图标.ico"
        legacy_png = project_root / "图标.png"
        if legacy_ico.exists():
            root.iconbitmap(default=str(legacy_ico))
        if legacy_png.exists():
            icon_image = tk.PhotoImage(file=str(legacy_png))
            root.iconphoto(True, icon_image)
            root._app_icon_image = icon_image  # type: ignore[attr-defined]
    except tk.TclError:
        pass
    _apply_windows_titlebar_icon(root, icon_ico if icon_ico.exists() else None)


def _apply_windows_titlebar_icon(root: tk.Tk, icon_path: Path | None) -> None:
    if not icon_path:
        return
    try:
        root.update_idletasks()
        hwnd = root.winfo_id()
        user32 = ctypes.windll.user32
        image_icon = 1
        lr_loadfromfile = 0x00000010
        wm_seticon = 0x0080
        icon_small = 0
        icon_big = 1

        user32.LoadImageW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        user32.LoadImageW.restype = ctypes.c_void_p
        user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
        user32.SendMessageW.restype = ctypes.c_void_p

        small_icon = user32.LoadImageW(None, str(icon_path), image_icon, 16, 16, lr_loadfromfile)
        big_icon = user32.LoadImageW(None, str(icon_path), image_icon, 32, 32, lr_loadfromfile)
        if small_icon:
            user32.SendMessageW(hwnd, wm_seticon, icon_small, small_icon)
        if big_icon:
            user32.SendMessageW(hwnd, wm_seticon, icon_big, big_icon)
        root._small_hicon = small_icon  # type: ignore[attr-defined]
        root._big_hicon = big_icon  # type: ignore[attr-defined]
    except Exception:
        pass
