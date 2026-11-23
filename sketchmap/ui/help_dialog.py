from pathlib import Path

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QPushButton, QHBoxLayout

MANUAL = Path(__file__).resolve().parent.parent / "docs" / "USER_MANUAL.md"


class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SketchMap user manual")
        self.resize(820, 680)
        v = QVBoxLayout(self)
        tb = QTextBrowser()
        tb.setOpenExternalLinks(True)
        tb.setSearchPaths([str(MANUAL.parent)])
        try:
            tb.setMarkdown(MANUAL.read_text(encoding="utf-8"))
        except OSError:
            tb.setPlainText("The user manual file is missing from this installation (sketchmap/docs/USER_MANUAL.md).")
        v.addWidget(tb)
        row = QHBoxLayout()
        row.addStretch(1)
        b = QPushButton("Close")
        b.clicked.connect(self.accept)
        row.addWidget(b)
        v.addLayout(row)
