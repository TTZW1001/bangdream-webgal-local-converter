from __future__ import annotations

from pathlib import Path

from .converter import convert_text


class MainWindow:  # pragma: no cover - GUI smoke-tested manually
    def __init__(self, config_dir: Path) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QFileDialog,
            QHBoxLayout,
            QLabel,
            QListWidget,
            QMainWindow,
            QPushButton,
            QPlainTextEdit,
            QVBoxLayout,
            QWidget,
        )

        self.config_dir = config_dir
        self.window = QMainWindow()
        self.window.setWindowTitle("Fanfic2WebGAL Local Converter")
        self.window.resize(1180, 760)

        self.input_edit = QPlainTextEdit()
        self.input_edit.setPlaceholderText("粘贴同人文或导入 txt")
        self.output_edit = QPlainTextEdit()
        self.output_edit.setPlaceholderText("生成的 WebGAL 脚本会显示在这里")
        self.pending_list = QListWidget()

        import_button = QPushButton("导入文本")
        import_button.clicked.connect(self.import_text)
        generate_button = QPushButton("生成脚本")
        generate_button.clicked.connect(self.generate_script)
        export_button = QPushButton("导出脚本")
        export_button.clicked.connect(self.export_script)

        toolbar = QHBoxLayout()
        toolbar.addWidget(import_button)
        toolbar.addWidget(generate_button)
        toolbar.addWidget(export_button)
        toolbar.addStretch(1)

        editors = QHBoxLayout()
        left_box = QVBoxLayout()
        left_box.addWidget(QLabel("原文"))
        left_box.addWidget(self.input_edit)
        right_box = QVBoxLayout()
        right_box.addWidget(QLabel("生成结果"))
        right_box.addWidget(self.output_edit)
        editors.addLayout(left_box, 1)
        editors.addLayout(right_box, 1)

        root = QVBoxLayout()
        root.addLayout(toolbar)
        root.addLayout(editors, 1)
        root.addWidget(QLabel("待确认项"))
        root.addWidget(self.pending_list)

        container = QWidget()
        container.setLayout(root)
        self.window.setCentralWidget(container)
        self.window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

    def show(self) -> None:
        self.window.show()

    def import_text(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(self.window, "导入文本", "", "Text Files (*.txt);;All Files (*)")
        if path:
            self.input_edit.setPlainText(Path(path).read_text(encoding="utf-8-sig"))

    def generate_script(self) -> None:
        self.pending_list.clear()
        result = convert_text(self.input_edit.toPlainText(), self.config_dir)
        self.output_edit.setPlainText(result.script)
        for item in result.pending_items:
            self.pending_list.addItem(f"#{item.index} {item.issue_type}: {item.raw} | {item.suggestion}")

    def export_script(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getSaveFileName(self.window, "导出脚本", "scene.txt", "Text Files (*.txt);;All Files (*)")
        if path:
            Path(path).write_text(self.output_edit.toPlainText(), encoding="utf-8", newline="\n")


def main(config_dir: Path) -> int:  # pragma: no cover - GUI entry point
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        raise SystemExit("PySide6 is not installed. Run `pip install -r requirements.txt` or use CLI mode.") from exc

    app = QApplication([])
    window = MainWindow(config_dir)
    window.show()
    return app.exec()
