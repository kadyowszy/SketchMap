import dataclasses
import os
import sys

import numpy as np

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QActionGroup, QFont, QKeySequence, QShortcut, QPixmap, QIcon
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
                             QStackedWidget, QButtonGroup, QFileDialog, QMessageBox, QMenu)

from ..config import Config, PreprocessParams
from ..pipeline import run_pipeline, build_model, suggest_cell_mm
from ..preprocess import load_image, limit_side
from ..thinning import zhang_suen
from ..reachability import model_unreachable
from .adjust_dialog import AdjustDialog
from ..elements import check as check_level
from ..exporters import save_json, save_tscn, sheet_conflict, existing_outputs
from ..tileset import load_tileset, write_template, default_spec
from .tileset_dialog import TilesetCustomizerDialog
from .help_dialog import HelpDialog
from .settings import SettingsDialog
from . import settings
from ..version import __version__, VERSION_LABEL, APP_TAGLINE
from .. import beta
from . import icons, theme
from .level_io import load_level, overlay_rgba
from .pages.edit import EditPage
from .pages.files import FilesPage
from .pages.home import HomePage
from .pages.library import LibraryPage
from .pages.templates import TemplatesPage
from .qtutil import to_pixmap
from .store import RecentStore, kind_of
from .widgets import NavButton, IconButton, Toast

IMG_FILTER = "Sketch images (*.png *.jpg *.jpeg)"
OPEN_FILTER = "Sketch or level (*.png *.jpg *.jpeg *.json);;Sketch images (*.png *.jpg *.jpeg);;Level files (*.json)"

HOME, EDIT, LIBRARY, FILES, TEMPLATES = range(5)


STAGE_PAUSE_MS = 60


class Worker(QThread):
    done = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, str)

    def __init__(self, path, cfg, cell_mm, prepared=False, prep_params=None):
        super().__init__()
        self.path, self.cfg, self.cell_mm, self.prepared = path, cfg, cell_mm, prepared
        self.prep_params = prep_params

    def _report(self, pct, text):
        self.progress.emit(int(pct), text)
        if STAGE_PAUSE_MS:
            self.msleep(STAGE_PAUSE_MS)

    def run(self):
        try:
            self.done.emit(run_pipeline(self.path, self.cfg, self.cell_mm, progress=self._report, prepared=self.prepared,
                                          prep_params=self.prep_params))
        except Exception as ex:
            self.failed.emit(str(ex))


class MainWindow(QMainWindow):
    tileset_changed = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"SketchMap {VERSION_LABEL}")
        self.resize(1380, 860)
        self.setMinimumSize(1120, 700)
        self.setAcceptDrops(True)

        self.cfg = Config()
        self.tileset = None
        self.recent = RecentStore()
        self.A = self.model = self.st = self.worker = None
        self.prep_params = PreprocessParams()
        self.source = None
        self.auto_counts = {}
        self._edit_after_load = False
        self._last_dir = settings.get("export_dir")
        self._dirty = False

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self._build_sidebar())
        self.pages = QStackedWidget()
        h.addWidget(self.pages, 1)

        self.home, self.edit = HomePage(), EditPage()
        self.library, self.files, self.templates = LibraryPage(), FilesPage(self.recent), TemplatesPage()
        for p in (self.home, self.edit, self.library, self.files, self.templates):
            self.pages.addWidget(p)
        self.files.refresh()
        self.toast = Toast(root)
        self.edit.spin.setValue(settings.get("cell_mm"))

        self.home.panel.import_clicked.connect(self.import_dialog)
        self.home.panel.open_clicked.connect(self.open_dialog)
        self.home.edit_clicked.connect(self.go_edit)
        self.home.export_chosen.connect(self.export)
        self.edit.back_clicked.connect(lambda: self.go("home"))
        self.edit.export_chosen.connect(self.export)
        self.edit.scale_requested.connect(self.on_scale_requested)
        self.edit.auto_scale_requested.connect(self.auto_scale)
        self.edit.stats_toggled.connect(self.on_stats_toggled)
        self.edit.stage_changed.connect(self.refresh_stats)
        self.edit.edited.connect(self.on_edited)
        self.edit.customize_tileset_requested.connect(self.customize_tileset)
        self.tileset_changed.connect(self.edit.view.set_tileset)
        self.edit.view.set_tileset(None)
        self.files.open_requested.connect(lambda p: self.open_path(p))
        self.files.edit_requested.connect(lambda p: self.open_path(p, then_edit=True))
        self.templates.use_requested.connect(lambda p: self.open_path(p))

        for seq, fn in (("Ctrl+O", self.import_dialog), ("Ctrl+Z", self._undo), ("Ctrl+Y", self._redo),
                        ("Ctrl+Shift+Z", self._redo), ("Ctrl+I", self._toggle_stats), ("F1", self._manual)):
            QShortcut(QKeySequence(seq), self, activated=fn)

        self.go("home")

    def _build_sidebar(self):
        sb = QFrame()
        sb.setObjectName("sidebar")
        sb.setFixedWidth(96)
        v = QVBoxLayout(sb)
        v.setContentsMargins(0, 22, 0, 18)
        v.setSpacing(6)
        logo = QLabel()
        logo.setPixmap(icons.logo_pixmap(44))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(logo)
        v.addSpacing(30)
        self.nav = {}
        grp = QButtonGroup(self)
        grp.setExclusive(True)
        for key, icon_name, label in (("home", "home", "Home"), ("library", "library", "Library"),
                                      ("files", "files", "Files"), ("templates", "templates", "Templates")):
            b = NavButton(icon_name, label)
            grp.addButton(b)
            b.clicked.connect(lambda _=False, k=key: self.go(k))
            v.addWidget(b)
            self.nav[key] = b
        v.addStretch(1)
        menu = IconButton("menu", 24, "Menu", variant="round", norm="text")
        menu.setFixedSize(48, 48)
        menu.clicked.connect(self._open_menu)
        v.addWidget(menu, 0, Qt.AlignmentFlag.AlignHCenter)
        self._menu_btn = menu
        return sb

    def _open_menu(self):
        m = QMenu(self)
        m.addAction("User manual").triggered.connect(self._manual)
        m.addAction("Symbol legend").triggered.connect(lambda: self.go("library"))
        m.addAction("Keyboard shortcuts").triggered.connect(self._shortcuts)
        m.addSeparator()
        tm = m.addMenu("Theme")
        grp = QActionGroup(tm)
        for key, label in theme.THEME_CHOICES:
            a = tm.addAction(label)
            a.setCheckable(True)
            a.setChecked(key == theme.current_choice())
            grp.addAction(a)
            a.triggered.connect(lambda _=False, k=key: self._set_theme(k))
        m.addAction("Settings…").triggered.connect(self._settings)
        m.addSeparator()
        m.addAction("About SketchMap").triggered.connect(self._about)
        m.exec(self._menu_btn.mapToGlobal(self._menu_btn.rect().topRight()))

    def _manual(self):
        HelpDialog(self).exec()

    def _set_theme(self, key):
        theme.apply_theme(key)
        self.notify(f"Theme: {dict(theme.THEME_CHOICES)[key]}.", "success")

    def _settings(self):
        if SettingsDialog(self).exec() == SettingsDialog.DialogCode.Accepted:
            self.edit.spin.setValue(settings.get("cell_mm"))
            self.notify("Settings saved.", "success")

    def _about(self):
        box = QMessageBox(self)
        box.setWindowTitle("About SketchMap")
        box.setIconPixmap(icons.logo_pixmap(84))
        box.setText(f"<b>SketchMap {VERSION_LABEL}</b><br>"
                    "Beta: only Boundary, Wall, Player start, Enemy spawn and Door are recognized from photos.<br><br>"
                    "Kurt Yhuri P. Edañol (Documentation)<br>"
                    "Jankaizen I. Dezosa (Designer)<br>"
                    "Samuel Lance M. Panganiban (Developer)")
        box.exec()

    def _shortcuts(self):
        QMessageBox.information(self, "Keyboard shortcuts",
                                "Ctrl+O  Import a sketch\nCtrl+Z / Ctrl+Y  Undo / redo (Edit page)\nCtrl+I  Stats for nerds (Edit page)\n"
                                "F1  User manual\n"
                                "Mouse wheel  Zoom   ·   Space or middle mouse  Pan   ·   F  Fit to screen")

    def go(self, name):
        idx = dict(home=HOME, library=LIBRARY, files=FILES, templates=TEMPLATES, edit=EDIT)[name]
        self.pages.setCurrentIndex(idx)
        self.nav["home" if name == "edit" else name].setChecked(True)
        if name == "files":
            self.files.refresh()
        elif name == "home":
            self.home.level_view.update()

    def go_edit(self):
        if self.model is not None:
            self.go("edit")

    def notify(self, text, kind="info"):
        self.toast.show_message(text, kind)

    def import_dialog(self):
        p, _ = QFileDialog.getOpenFileName(self, "Import sketch", self._last_dir, IMG_FILTER)
        if p:
            self.open_path(p)

    def open_dialog(self):
        p, _ = QFileDialog.getOpenFileName(self, "Open file", self._last_dir, OPEN_FILTER)
        if p:
            self.open_path(p)

    def open_path(self, path, then_edit=False):
        if not os.path.isfile(path):
            self.notify("That file no longer exists on disk.", "error")
            return
        if not self._discard_ok("open another file"):
            return
        self._last_dir = os.path.dirname(path)
        kind = kind_of(path)
        if kind == "sketch":
            self.load(path, then_edit)
        elif kind == "level":
            self.open_level(path, then_edit)
        else:
            self.notify("Unsupported file. Use PNG, JPG, JPEG or a level .json.", "error")

    def load(self, path, then_edit=False):
        if self.worker is not None and self.worker.isRunning():
            self.notify("Still digitalizing the previous sketch, one moment…")
            return
        try:
            raw = load_image(path)
        except Exception as ex:
            self.notify("Could not open that image.", "error")
            QMessageBox.warning(self, "Cannot open image", str(ex))
            return
        shown = limit_side(raw)
        start = dataclasses.replace(self.prep_params, perspective_points=None)
        dlg = AdjustDialog(shown, initial_params=start, thinning_preview_fn=self._thinning_preview, parent=self)
        if dlg.exec() != AdjustDialog.DialogCode.Accepted:
            return
        self.prep_params = dlg.get_params()

        self._edit_after_load = then_edit
        self.source = path
        self.go("home")
        self.home.show_loading(os.path.basename(path))
        self.worker = Worker(shown, self.cfg, self.edit.spin.value(), prepared=True, prep_params=self.prep_params)
        self.worker.progress.connect(self.home.set_progress)
        self.worker.done.connect(self.on_done)
        self.worker.failed.connect(self.on_fail)
        self.worker.start()

    @staticmethod
    def _thinning_preview(mask):
        skel, _ = zhang_suen(mask)
        return (skel > 0).astype(np.uint8) * 255

    def on_fail(self, msg):
        if self.model is not None:
            self.home.show_preview(None, self.model, None, self._subtitle())
        else:
            self.home.show_empty()
        self.notify("Could not process that sketch.", "error")
        QMessageBox.warning(self, "Cannot process sketch", msg)

    def on_done(self, res):
        self._dirty = False
        self.A, self.model, self.st = res
        self.auto_counts = self.model.counts()
        overlay = self._make_overlay()
        name = os.path.basename(self.source)
        self.edit.set_level(self.model, self.A, self.st, overlay, self.model.scale.get("cell_mm", self.cfg.cell_mm))
        self.home.show_preview(to_pixmap(self.A.previews["original"]), self.model, None, self._subtitle())
        self.setWindowTitle(f"SketchMap {VERSION_LABEL}  ·  {self.source}")
        self._update_summary()
        self.recent.touch(self.source, "sketch")
        self.files.refresh()
        n = len(self.A.warnings)
        self.notify(f"Digitalized {name}" + (f"  ·  {n} warning{'s' if n != 1 else ''}, see Stats for nerds" if n else ""),
                    "success")
        if self.edit.stats_visible():
            self.refresh_stats()
        if self._edit_after_load:
            self.go("edit")

    def open_level(self, path, then_edit=False):
        try:
            model = load_level(path)
        except (OSError, ValueError) as ex:
            self.notify("Could not open that level file.", "error")
            QMessageBox.warning(self, "Cannot open level", str(ex))
            return
        self._dirty = False
        self.A = self.st = None
        self.model, self.source, self.auto_counts = model, path, model.counts()
        self.edit.set_level(model, None, None, None, model.scale.get("cell_mm", self.cfg.cell_mm))
        self.home.show_preview(None, model, None, self._subtitle())
        self.setWindowTitle(f"SketchMap {VERSION_LABEL}  ·  {path}")
        self._update_summary()
        self.recent.touch(path, "level")
        self.files.refresh()
        self.notify(f"Opened {os.path.basename(path)}", "success")
        if model.notes:
            QMessageBox.information(self, "Older level converted", "\n".join(model.notes))
        self.go("edit" if then_edit else "home")

    def _make_overlay(self):
        try:
            return overlay_rgba(self.model, self.A)
        except Exception:
            return None

    def on_scale_requested(self, mm):
        if not self.A or not self.model or abs(mm - self.model.scale.get("cell_mm", 0)) < 1e-6:
            return
        if self.model.edits:
            ans = QMessageBox.question(self, "Re-map grid",
                                       "Changing the scale re-maps the grid and discards your manual edits. Continue?")
            if ans != QMessageBox.StandardButton.Yes:
                self.edit.set_scale_value(self.model.scale["cell_mm"])
                return
        self.model = build_model(self.A, self.cfg, mm, self.st)
        self.auto_counts = self.model.counts()
        self.edit.set_level(self.model, self.A, self.st, self._make_overlay(), mm)
        self.home.level_view.set_model(self.model, None)
        self.home.set_subtitle(self._subtitle())
        self._update_summary()
        if self.edit.stats_visible():
            self.refresh_stats()
        self.notify(f"Grid re-mapped at 1 cell = {mm:.1f} mm  ·  {self.model.width} × {self.model.height} tiles")

    def auto_scale(self):
        if not self.A:
            return
        s = suggest_cell_mm(self.A)
        if s is None:
            QMessageBox.information(self, "Auto scale",
                                    "Need at least 2 symbols (star, square or triangle) to estimate the tile size.")
            return
        mm = round(s, 1)
        self.edit.set_scale_value(mm)
        self.on_scale_requested(mm)

    def on_edited(self):
        if self.model is None:
            return
        self._dirty = True
        self.home.level_view.update()
        self._update_summary()
        if self.edit.stats_visible():
            self.refresh_stats()

    def _subtitle(self):
        m = self.model
        parts = [os.path.basename(self.source or ""), f"{m.width} × {m.height} tiles", f"{m.size_class(self.cfg)} map"]
        if self.st:
            parts.append(f"processed in {self.st.total_ms():.0f} ms")
        return "  ·  ".join(p for p in parts if p)

    def _update_summary(self):
        m = self.model
        if m is None:
            return
        txt = f"{m.width} × {m.height} tiles  ·  {m.size_class(self.cfg)} map"
        if m.edits:
            txt += f"  ·  {m.edits} edit{'s' if m.edits != 1 else ''}"
        bad = model_unreachable(m)
        self.edit.view.set_highlight(bad)
        if bad:
            txt += f"  ·  {len(bad)} floor tile{'s' if len(bad) != 1 else ''} unreachable from the player start (red)"
        warns = check_level(m)
        if warns:
            txt += f"  ·  {len(warns)} design warning{'s' if len(warns) != 1 else ''}"
        self.edit.set_summary(txt)

    def on_stats_toggled(self, on):
        if on:
            self.refresh_stats()

    def refresh_stats(self):
        if not self.st or self.model is None:
            return
        m, c0, c1 = self.model, self.auto_counts, self.model.counts()
        extra = []
        if self.A is not None and self.A.warnings:
            extra += ["== Warnings =="] + [f"  {w}" for w in self.A.warnings] + [""]
        extra += ["== Manual editing ==", f"  net edits since detection: {m.edits}  (undo stack {len(self.edit.view.undo_stack)})"]
        extra += [f"  {k:<14} detected {c0.get(k, 0):>3} -> now {c1[k]:>3}  ({c1[k] - c0.get(k, 0):+d})" for k in c1]
        extra.append("  every edit is snapped to the H/V axis, so lines stay perpendicular")
        bad = model_unreachable(m)
        extra += ["", "== Playability =="]
        extra.append("  no player start placed: reachability not checked" if bad is None else
                     f"  floor tiles not reachable from the player start (4-way flood fill): {len(bad)}")
        extra += [f"  design: {w}" for w in check_level(m)]
        self.edit.drawer.show_text(self.st.render(extra, only=self.edit.drawer.stage()))

    def _toggle_stats(self):
        if self.pages.currentIndex() == EDIT:
            self.edit.toggle_stats()

    def _undo(self):
        if self.pages.currentIndex() == EDIT and self.edit.undo_btn.isEnabled():
            self.edit.view.undo()

    def _redo(self):
        if self.pages.currentIndex() == EDIT and self.edit.redo_btn.isEnabled():
            self.edit.view.redo()

    def set_tileset(self, spec):
        self.tileset = spec
        self.tileset_changed.emit(spec)

    def customize_tileset(self):
        dlg = TilesetCustomizerDialog(self.tileset or default_spec(), self)
        if dlg.exec():
            self.set_tileset(dlg.spec)
            self.edit.tiles_sw.setChecked(True)
            self.notify(f"Tileset set: {os.path.basename(dlg.spec.image_path)}. It applies to .tscn and .json exports.", "success")

    def _tileset_action(self, act):
        if act == "tileset_customize":
            self.customize_tileset()
        elif act == "tileset_reset":
            self.set_tileset(None)
            self.notify("Using the built-in tileset.", "success")
        elif act == "tileset_template":
            d = QFileDialog.getExistingDirectory(self, "Save tileset template to…", self._last_dir or "")
            if d:
                try:
                    png, _ = write_template(d)
                except OSError as ex:
                    QMessageBox.critical(self, "Cannot save template", str(ex))
                    return
                self.notify(f"Saved {os.path.basename(png)} + manifest. Repaint it, then pick it with 'Custom tileset'.", "success")
        else:
            p, _ = QFileDialog.getOpenFileName(self, "Choose a tileset", self._last_dir or "",
                                               "Tileset (*.png *.jpg *.jpeg *.json)")
            if p:
                try:
                    spec = load_tileset(p)
                except ValueError as ex:
                    QMessageBox.warning(self, "Cannot use that tileset", str(ex))
                    return
                self.set_tileset(spec)
                self.notify(f"Tileset set: {os.path.basename(spec.image_path)}. It applies to .tscn and .json exports.", "success")

    def export(self, fmt):
        if fmt.startswith("tileset"):
            return self._tileset_action(fmt)
        if self.model is None:
            self.notify("Import a sketch first.", "error")
            return
        base = os.path.splitext(os.path.basename(self.source or "level"))[0] + "." + fmt
        start = os.path.join(self._last_dir, base) if self._last_dir else base
        filt = "JSON (*.json)" if fmt == "json" else "Godot scene (*.tscn)"
        p, _ = QFileDialog.getSaveFileName(self, f"Export as .{fmt}", start, filt,
                                           options=QFileDialog.Option.DontConfirmOverwrite)
        if not p:
            return
        if not p.lower().endswith("." + fmt):
            p += "." + fmt
        if not self._confirm_replace(existing_outputs(p, fmt)):
            return
        overwrite = False
        clash = sheet_conflict(p, self.tileset)
        if clash:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Question)
            box.setWindowTitle("Sprite sheet already exists")
            box.setText(f"A different '{os.path.basename(clash)}' is already in that folder.\n\n"
                        "Replace it with the sheet from your tileset, or keep the existing one? "
                        "If you keep it, the exported level will use the existing picture.")
            rep = box.addButton("Replace it", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Keep existing", QMessageBox.ButtonRole.DestructiveRole)
            cancel = box.addButton(QMessageBox.StandardButton.Cancel)
            box.exec()
            if box.clickedButton() is cancel:
                return
            overwrite = box.clickedButton() is rep
        try:
            if fmt == "json":
                save_json(p, self.model, self.cfg, self.tileset, overwrite)
            else:
                save_tscn(p, self.model, self.cfg, self.tileset, overwrite)
        except OSError as ex:
            QMessageBox.critical(self, "Export failed", f"Invalid or inaccessible export path:\n{ex}")
            return
        self._dirty = False
        warns = check_level(self.model)
        self.notify(f"Exported {os.path.basename(p)}" + (f"  ·  {len(warns)} design warning{'s' if len(warns) != 1 else ''}" if warns else ""),
                    "success")
        if warns:
            QMessageBox.information(self, "Exported, but the level is incomplete", "\n".join("• " + w for w in warns))

    def _confirm_replace(self, files):
        if not files:
            return True
        names = "\n".join("• " + os.path.basename(f) for f in files)
        r = QMessageBox.question(self, "Replace existing files?",
                                 f"These files already exist in that folder and will be replaced:\n\n{names}",
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                 QMessageBox.StandardButton.Cancel)
        return r == QMessageBox.StandardButton.Yes

    def _discard_ok(self, what):
        if not self._dirty or not settings.get("confirm_discard"):
            return True
        r = QMessageBox.question(self, "Unsaved edits",
                                 f"You edited the map by hand and have not exported it.\n\nDiscard those edits and {what}?",
                                 QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                 QMessageBox.StandardButton.Cancel)
        return r == QMessageBox.StandardButton.Discard

    def dragEnterEvent(self, e):
        urls = e.mimeData().urls() if e.mimeData().hasUrls() else []
        if any(u.isLocalFile() for u in urls):
            e.acceptProposedAction()
            self.home.panel.set_dragging(True)

    def dragLeaveEvent(self, e):
        self.home.panel.set_dragging(False)

    def dropEvent(self, e):
        self.home.panel.set_dragging(False)
        for u in e.mimeData().urls():
            if u.isLocalFile():
                e.acceptProposedAction()
                self.open_path(u.toLocalFile())
                return

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "toast"):
            self.toast.reposition()

    def closeEvent(self, e):
        if not self._discard_ok("close SketchMap"):
            e.ignore()
            return
        if self.worker is not None and self.worker.isRunning():
            self.worker.wait(3000)
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SketchMap")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(QIcon(icons.logo_pixmap(128)))
    app.setStyle("Fusion")
    theme.setup_fonts()
    app.setFont(QFont(theme.FONT["ui"], 10))
    theme.apply_theme(settings.get("theme"), app, save=False)
    theme.follow_system(app)
    w = MainWindow()
    w.show()
    if len(sys.argv) > 1:
        w.open_path(sys.argv[1])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
