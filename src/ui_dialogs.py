from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from .models import SegmentKind


def open_speaker_picker_dialog(app: Any, segment_order: int) -> None:
    segment = app.last_result.segments[segment_order] if app.last_result and segment_order < len(app.last_result.segments) else None
    window = tk.Toplevel(app.root)
    segment_kind = "对白" if segment and segment.kind == SegmentKind.DIALOGUE else "旁白"
    window.title(f"修正{segment_kind} #{segment_order}")
    window.geometry("420x520")
    window.configure(bg=app.colors["window"])

    ttk.Label(window, text="选择角色", style="PanelTitle.TLabel").pack(anchor="w", padx=12, pady=(12, 4))
    character_list = tk.Listbox(
        window,
        font=app.ui_font,
        bg=app.colors["list_bg"],
        fg=app.colors["text"],
        selectbackground=app.colors["primary"],
        selectforeground="#ffffff",
        relief=tk.SOLID,
        bd=1,
        activestyle="none",
    )
    character_list.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 10))
    entries = sorted(
        app.config.characters.items(),
        key=lambda item: (item[1].band or "", item[1].generic_character_id or "999", item[0]),
    )
    for character_id, character in entries:
        label = f"{character.display_name} ({character_id})"
        if character.band:
            label += f" - {character.band}"
        character_list.insert(tk.END, label)

    def apply_choice() -> None:
        selection = character_list.curselection()
        if not selection:
            return
        character_id = entries[selection[0]][0]
        app.speaker_overrides[segment_order] = f"char:{character_id}"
        window.destroy()
        app.generate_script()

    ttk.Label(window, text="或输入自定义名字", style="PanelTitle.TLabel").pack(anchor="w", padx=12)
    custom_var = tk.StringVar(value="")
    custom_entry = tk.Entry(
        window,
        textvariable=custom_var,
        font=app.ui_font,
        bg=app.colors["panel"],
        fg=app.colors["text"],
        insertbackground=app.colors["primary"],
        relief=tk.SOLID,
        bd=1,
    )
    custom_entry.pack(fill=tk.X, padx=12, pady=(4, 10))

    def apply_custom_name() -> None:
        custom_name = custom_var.get().strip()
        if not custom_name:
            messagebox.showinfo("缺少名字", "请输入自定义说话人名字。")
            return
        app.speaker_overrides[segment_order] = f"name:{custom_name}"
        window.destroy()
        app.generate_script()

    def clear_choice() -> None:
        app.speaker_overrides.pop(segment_order, None)
        window.destroy()
        app.generate_script()

    def apply_narration() -> None:
        app.speaker_overrides[segment_order] = "kind:narration"
        window.destroy()
        app.generate_script()

    buttons = tk.Frame(window, bg=app.colors["window"])
    buttons.pack(fill=tk.X, padx=12, pady=(0, 12))
    ttk.Button(buttons, text="应用并重生成", command=apply_choice, style="Primary.TButton").pack(side=tk.LEFT)
    ttk.Button(buttons, text="应用自定义", command=apply_custom_name, style="Secondary.TButton").pack(side=tk.LEFT, padx=(8, 0))
    ttk.Button(buttons, text="标记为旁白", command=apply_narration, style="Quiet.TButton").pack(side=tk.LEFT, padx=(8, 0))
    ttk.Button(buttons, text="清除此句修正", command=clear_choice, style="Quiet.TButton").pack(side=tk.LEFT, padx=(8, 0))

    current = app.speaker_overrides.get(segment_order)
    if current:
        if current == "kind:narration":
            pass
        elif current.startswith("name:"):
            custom_var.set(current[5:])
        else:
            current_id = current[5:] if current.startswith("char:") else current
            for index, (character_id, _character) in enumerate(entries):
                if character_id == current_id:
                    character_list.selection_set(index)
                    character_list.see(index)
                    break
    custom_entry.focus_set()


def open_figure_event_editor_dialog(app: Any, line_number: int) -> None:
    event_info = app.output_figure_events.get(line_number)
    if not event_info:
        messagebox.showinfo("请选择立绘行", "请先选择或双击一行 changeFigure 立绘脚本。")
        return
    figure_event_index, character_id = event_info
    character = app.config.characters.get(character_id)
    if character is None:
        return

    window = tk.Toplevel(app.root)
    window.title(f"立绘微调 #{figure_event_index} {character.display_name}")
    window.geometry("460x360")
    window.configure(bg=app.colors["window"])

    override = app.figure_event_overrides.get(figure_event_index, {})
    keys = ["默认"] + sorted(set(character.models_31.keys()) | set(character.models_generic.keys()))
    model_var = tk.StringVar(value=override.get("model_key", "默认"))
    motion_var = tk.StringVar(value=override.get("motion", ""))
    expression_var = tk.StringVar(value=override.get("expression", ""))
    position_var = tk.StringVar(value=override.get("position", "auto"))

    ttk.Label(window, text=f"角色：{character.display_name} ({character_id})", style="PanelTitle.TLabel").pack(anchor="w", padx=12, pady=(12, 4))
    form = tk.Frame(window, bg=app.colors["window"])
    form.pack(fill=tk.X, padx=12, pady=8)

    ttk.Label(form, text="模型键", style="Toolbar.TLabel").grid(row=0, column=0, sticky="w", pady=5)
    app._make_combobox(form, model_var, keys).grid(row=0, column=1, sticky="ew", pady=5)
    ttk.Label(form, text="动作", style="Toolbar.TLabel").grid(row=1, column=0, sticky="w", pady=5)
    ttk.Entry(form, textvariable=motion_var, font=app.ui_font).grid(row=1, column=1, sticky="ew", pady=5)
    ttk.Label(form, text="表情", style="Toolbar.TLabel").grid(row=2, column=0, sticky="w", pady=5)
    ttk.Entry(form, textvariable=expression_var, font=app.ui_font).grid(row=2, column=1, sticky="ew", pady=5)
    ttk.Label(form, text="位置", style="Toolbar.TLabel").grid(row=3, column=0, sticky="w", pady=5)
    app._make_combobox(form, position_var, ("auto", "-left", "-right")).grid(row=3, column=1, sticky="ew", pady=5)
    form.columnconfigure(1, weight=1)

    current_line = app.output_text.get(f"{line_number}.0", f"{line_number}.end")
    ttk.Label(window, text=current_line, wraplength=430, justify=tk.LEFT, style="Toolbar.TLabel").pack(anchor="w", padx=12, pady=(4, 8))

    def apply_override() -> None:
        control: dict[str, str] = {}
        if model_var.get() and model_var.get() != "默认":
            control["model_key"] = model_var.get()
        if motion_var.get().strip():
            control["motion"] = motion_var.get().strip()
        if expression_var.get().strip():
            control["expression"] = expression_var.get().strip()
        if position_var.get() in {"-left", "-right"}:
            control["position"] = position_var.get()
        if control:
            app.figure_event_overrides[figure_event_index] = control
        else:
            app.figure_event_overrides.pop(figure_event_index, None)
        window.destroy()
        app.generate_script()

    def clear_override() -> None:
        app.figure_event_overrides.pop(figure_event_index, None)
        window.destroy()
        app.generate_script()

    buttons = tk.Frame(window, bg=app.colors["window"])
    buttons.pack(fill=tk.X, padx=12, pady=(8, 0))
    ttk.Button(buttons, text="应用到这一行", command=apply_override, style="Primary.TButton").pack(side=tk.LEFT)
    ttk.Button(buttons, text="清除此行微调", command=clear_override, style="Quiet.TButton").pack(side=tk.LEFT, padx=(8, 0))


def open_scene_lock_settings_dialog(app: Any) -> None:
    if app.last_result is None:
        app.generate_script()
    if app.last_result is None:
        return

    window = tk.Toplevel(app.root)
    window.title("场景锁定设置")
    window.geometry("620x520")

    tk.Label(window, text="片段").pack(anchor="w", padx=8, pady=(8, 0))
    segment_list = tk.Listbox(window)
    segment_list.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    def segment_label(index: int) -> str:
        segment = app.last_result.segments[index]
        kind = "对白" if segment.kind == SegmentKind.DIALOGUE else "旁白"
        lock = app.segment_scene_locks.get(index)
        marker = f" [{lock}]" if lock else ""
        text = segment.text.replace("\n", " ")
        return f"#{index}{marker} {kind}: {text[:80]}"

    def refresh_segments() -> None:
        segment_list.delete(0, tk.END)
        for index, _segment in enumerate(app.last_result.segments):
            segment_list.insert(tk.END, segment_label(index))

    refresh_segments()

    editor = tk.Frame(window)
    editor.pack(fill=tk.X, padx=8, pady=(0, 8))
    tk.Label(editor, text="从所选片段开始锁定").pack(side=tk.LEFT)
    lock_var = tk.StringVar(value="")
    tk.Entry(editor, textvariable=lock_var, width=28).pack(side=tk.LEFT, padx=(8, 0))

    def selected_segment_order() -> int | None:
        selection = segment_list.curselection()
        if not selection:
            return None
        return selection[0]

    def apply_lock() -> None:
        segment_order = selected_segment_order()
        value = lock_var.get().strip()
        if segment_order is None or not value:
            return
        app.segment_scene_locks[segment_order] = value
        refresh_segments()
        app.generate_script()

    def release_lock() -> None:
        segment_order = selected_segment_order()
        if segment_order is None:
            return
        app.segment_scene_locks[segment_order] = "auto"
        refresh_segments()
        app.generate_script()

    def clear_locks() -> None:
        app.segment_scene_locks.clear()
        refresh_segments()
        app.generate_script()

    buttons = tk.Frame(window)
    buttons.pack(fill=tk.X, padx=8, pady=(0, 8))
    tk.Button(buttons, text="应用锁定", command=apply_lock).pack(side=tk.LEFT)
    tk.Button(buttons, text="从此解除锁定", command=release_lock).pack(side=tk.LEFT, padx=(8, 0))
    tk.Button(buttons, text="清空片段锁定", command=clear_locks).pack(side=tk.LEFT, padx=(8, 0))

    def fill_current_lock(_event: object | None = None) -> None:
        segment_order = selected_segment_order()
        if segment_order is None:
            return
        value = app.segment_scene_locks.get(segment_order, "")
        lock_var.set("" if value == "auto" else value)

    segment_list.bind("<<ListboxSelect>>", fill_current_lock)


def open_figure_control_settings_dialog(app: Any) -> None:
    window = tk.Toplevel(app.root)
    window.title("立绘控制")
    window.geometry("680x520")

    left = tk.Frame(window)
    left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=8)
    right = tk.Frame(window)
    right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=8, pady=8)

    tk.Label(left, text="角色").pack(anchor="w")
    character_list = tk.Listbox(left)
    character_list.pack(fill=tk.BOTH, expand=True)
    entries = sorted(
        app.config.characters.items(),
        key=lambda item: (item[1].band or "", item[1].generic_character_id or "999", item[0]),
    )
    for character_id, character in entries:
        marker = " *" if character_id in app.figure_controls else ""
        label = f"{character.display_name} ({character_id}){marker}"
        if character.band:
            label += f" - {character.band}"
        character_list.insert(tk.END, label)

    visibility_var = tk.StringVar(value="auto")
    position_var = tk.StringVar(value="auto")
    model_var = tk.StringVar(value="默认")
    tk.Label(right, text="显示").pack(anchor="w")
    tk.OptionMenu(right, visibility_var, "auto", "hide").pack(fill=tk.X)
    tk.Label(right, text="位置").pack(anchor="w", pady=(12, 0))
    tk.OptionMenu(right, position_var, "auto", "-left", "-right").pack(fill=tk.X)
    tk.Label(right, text="模型键").pack(anchor="w", pady=(12, 0))
    model_menu = tk.OptionMenu(right, model_var, "默认")
    model_menu.pack(fill=tk.X)

    def selected_character_id() -> str | None:
        selection = character_list.curselection()
        if not selection:
            return None
        return entries[selection[0]][0]

    def refresh_model_menu(character_id: str) -> None:
        character = app.config.characters[character_id]
        keys = ["默认"] + sorted(set(character.models_31.keys()) | set(character.models_generic.keys()))
        menu = model_menu["menu"]
        menu.delete(0, "end")
        for key in keys:
            menu.add_command(label=key, command=lambda value=key: model_var.set(value))

    def refresh_control(_event: object | None = None) -> None:
        character_id = selected_character_id()
        if not character_id:
            return
        refresh_model_menu(character_id)
        control = app.figure_controls.get(character_id, {})
        visibility_var.set(control.get("visibility", "auto"))
        position_var.set(control.get("position", "auto"))
        model_var.set(control.get("model_key", "默认"))

    def refresh_character_marks() -> None:
        current = character_list.curselection()
        character_list.delete(0, tk.END)
        for character_id, character in entries:
            marker = " *" if character_id in app.figure_controls else ""
            label = f"{character.display_name} ({character_id}){marker}"
            if character.band:
                label += f" - {character.band}"
            character_list.insert(tk.END, label)
        if current:
            character_list.selection_set(current[0])

    def build_control() -> dict[str, str]:
        control: dict[str, str] = {}
        if visibility_var.get() != "auto":
            control["visibility"] = visibility_var.get()
        if position_var.get() != "auto":
            control["position"] = position_var.get()
        if model_var.get() and model_var.get() != "默认":
            control["model_key"] = model_var.get()
        return control

    def set_character_control(character_id: str, control: dict[str, str]) -> None:
        if control:
            app.figure_controls[character_id] = control
        else:
            app.figure_controls.pop(character_id, None)

    def apply_control() -> None:
        character_id = selected_character_id()
        if not character_id:
            return
        set_character_control(character_id, build_control())
        refresh_character_marks()
        app.generate_script()

    def apply_to_appearing_characters() -> None:
        if app.last_result is None:
            app.generate_script()
        if app.last_result is None:
            return
        appearing_ids: list[str] = []
        for segment in app.last_result.segments:
            if segment.speaker_id and segment.speaker_id not in appearing_ids:
                appearing_ids.append(segment.speaker_id)
            for character_id in segment.mentioned_character_ids:
                if character_id in app.config.characters and character_id not in appearing_ids:
                    appearing_ids.append(character_id)
        if not appearing_ids:
            messagebox.showinfo("没有出场角色", "当前文本里还没有识别到可应用的角色。")
            return
        control = build_control()
        for character_id in appearing_ids:
            set_character_control(character_id, control)
        refresh_character_marks()
        app.generate_script()

    def apply_to_all_characters() -> None:
        control = build_control()
        if control:
            app.figure_controls["__all__"] = control
        else:
            app.figure_controls.pop("__all__", None)
        refresh_character_marks()
        app.generate_script()

    def clear_control() -> None:
        character_id = selected_character_id()
        if not character_id:
            return
        app.figure_controls.pop(character_id, None)
        refresh_character_marks()
        refresh_control()
        app.generate_script()

    def clear_all() -> None:
        app.figure_controls.clear()
        refresh_character_marks()
        refresh_control()
        app.generate_script()

    buttons = tk.Frame(right)
    buttons.pack(fill=tk.X, pady=(16, 0))
    tk.Button(buttons, text="应用到当前角色", command=apply_control).pack(side=tk.LEFT)
    tk.Button(buttons, text="清除此角色", command=clear_control).pack(side=tk.LEFT, padx=(8, 0))
    tk.Button(buttons, text="清空全部控制", command=clear_all).pack(side=tk.LEFT, padx=(8, 0))

    batch_buttons = tk.Frame(right)
    batch_buttons.pack(fill=tk.X, pady=(8, 0))
    tk.Button(batch_buttons, text="应用到全部出场角色", command=apply_to_appearing_characters).pack(side=tk.LEFT)
    tk.Button(batch_buttons, text="应用到全部角色", command=apply_to_all_characters).pack(side=tk.LEFT, padx=(8, 0))

    character_list.bind("<<ListboxSelect>>", refresh_control)
    if entries:
        character_list.selection_set(0)
        refresh_control()


def open_model_settings_dialog(app: Any) -> None:
    window = tk.Toplevel(app.root)
    window.title("模型设置")
    window.geometry("560x460")
    window.configure(bg=app.colors["window"])

    left = tk.Frame(window, bg=app.colors["window"])
    left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=8)
    right = tk.Frame(window, bg=app.colors["window"])
    right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=8, pady=8)

    ttk.Label(left, text="角色", style="PanelTitle.TLabel").pack(anchor="w", pady=(0, 4))
    character_list = tk.Listbox(left, font=app.ui_font, bg=app.colors["panel"], fg=app.colors["text"], relief=tk.SOLID, bd=1, activestyle="none")
    character_list.pack(fill=tk.BOTH, expand=True)

    entries = sorted(
        app.config.characters.items(),
        key=lambda item: (item[1].band or "", item[1].generic_character_id or "999", item[0]),
    )
    for character_id, character in entries:
        label = f"{character.display_name} ({character_id})"
        if character.band:
            label += f" - {character.band}"
        character_list.insert(tk.END, label)

    ttk.Label(right, text="模型键", style="PanelTitle.TLabel").pack(anchor="w", pady=(0, 4))
    model_var = tk.StringVar(value="")
    model_menu = app._make_combobox(right, model_var, ("默认",))
    model_menu.pack(fill=tk.X)
    current_label = ttk.Label(right, text="当前：默认", style="Toolbar.TLabel")
    current_label.pack(anchor="w", pady=(12, 8))

    def selected_character_id() -> str | None:
        selection = character_list.curselection()
        if not selection:
            return None
        return entries[selection[0]][0]

    def model_keys_for(character_id: str) -> list[str]:
        character = app.config.characters[character_id]
        keys = set(character.models_31.keys()) | set(character.models_generic.keys())
        return ["默认"] + sorted(keys)

    def refresh_models(_event: object | None = None) -> None:
        character_id = selected_character_id()
        if not character_id:
            return
        keys = model_keys_for(character_id)
        model_menu.configure(values=keys)
        current = app.model_overrides.get(character_id, "默认")
        model_var.set(current if current in keys else "默认")
        current_label.config(text=f"当前：{model_var.get()}")

    def apply_choice() -> None:
        character_id = selected_character_id()
        if not character_id:
            return
        value = model_var.get()
        if not value or value == "默认":
            app.model_overrides.pop(character_id, None)
        else:
            app.model_overrides[character_id] = value
        current_label.config(text=f"当前：{value or '默认'}")
        app.generate_script()

    def clear_model_overrides() -> None:
        app.model_overrides.clear()
        current_label.config(text="当前：默认")
        refresh_models()
        app.generate_script()

    ttk.Button(right, text="应用到角色", command=apply_choice, style="Primary.TButton").pack(anchor="w", pady=(8, 0))
    ttk.Button(right, text="清空全部覆盖", command=clear_model_overrides, style="Quiet.TButton").pack(anchor="w", pady=(8, 0))

    character_list.bind("<<ListboxSelect>>", refresh_models)
    if entries:
        character_list.selection_set(0)
        refresh_models()
