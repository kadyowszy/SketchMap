from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit, QPushButton,
                             QDoubleSpinBox, QFileDialog, QDialogButtonBox, QCheckBox, QComboBox)

from . import theme

DEFAULTS = dict(cell_mm=8.0, export_dir="", confirm_discard=True, theme="dark")


def _qs():
    return QSettings("SketchMap", "SketchMap")


def get(key):
    d = DEFAULTS[key]
    v = _qs().value(key, d)
    try:
        if isinstance(d, bool):
            return v if isinstance(v, bool) else str(v).lower() == "true"
        if isinstance(d, float):
            return float(v)
    except (TypeError, ValueError):
        return d
    return str(v) if v is not None else d


def put(key, value):
    _qs().setValue(key, value)


def reset():
    _qs().clear()


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(480)
        v = QVBoxLayout(self)
        form = QFormLayout()
        self.theme_box = QComboBox()
        for key, label in theme.THEME_CHOICES:
            self.theme_box.addItem(label, key)
        self.theme_box.setCurrentIndex(max(0, self.theme_box.findData(theme.current_choice())))
        form.addRow("Appearance", self.theme_box)
        self.cell = QDoubleSpinBox()
        self.cell.setRange(1.0, 100.0)
        self.cell.setDecimals(1)
        self.cell.setSuffix(" mm")
        self.cell.setValue(get("cell_mm"))
        form.addRow("Default tile size on paper", self.cell)
        row = QHBoxLayout()
        self.folder = QLineEdit(get("export_dir"))
        self.folder.setPlaceholderText("Ask every time (last used folder)")
        b = QPushButton("Browse…")
        b.clicked.connect(self._browse)
        row.addWidget(self.folder, 1)
        row.addWidget(b)
        form.addRow("Default export folder", row)
        self.confirm = QCheckBox("Ask before discarding unsaved manual edits")
        self.confirm.setChecked(get("confirm_discard"))
        form.addRow("", self.confirm)
        v.addLayout(form)
        note = QLabel("Settings are stored on this computer only. Nothing is ever sent over a network.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        v.addWidget(note)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
                              | QDialogButtonBox.StandardButton.RestoreDefaults)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(self._defaults)
        v.addWidget(bb)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Default export folder", self.folder.text() or "")
        if d:
            self.folder.setText(d)

    def _defaults(self):
        self.cell.setValue(DEFAULTS["cell_mm"])
        self.folder.clear()
        self.confirm.setChecked(DEFAULTS["confirm_discard"])
        self.theme_box.setCurrentIndex(self.theme_box.findData(DEFAULTS["theme"]))

    def _save(self):
        put("cell_mm", self.cell.value())
        put("export_dir", self.folder.text().strip())
        put("confirm_discard", self.confirm.isChecked())
        theme.apply_theme(self.theme_box.currentData())
        self.accept()
