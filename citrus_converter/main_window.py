"""
Elumichai — Main Window
================================
The primary application window with menu bar, status bar, and central
DropZone widget.
"""

import os
import shutil
import subprocess

from PySide6.QtCore import Qt, QSize, QMimeData, QUrl
from PySide6.QtGui import QKeySequence, QIcon, QAction
from PySide6.QtWidgets import (
    QMainWindow,
    QStatusBar,
    QMessageBox,
    QVBoxLayout,
    QWidget,
    QFileDialog,
    QInputDialog,
)

from citrus_converter.drop_zone import DropZone
from citrus_converter.radial_menu import RadialMenu
from citrus_converter.conversion_worker import ConversionWorker
from citrus_converter.settings_dialog import SettingsDialog
from citrus_converter.about_dialog import AboutDialog

# Colour tokens (duplicated here for convenience; canonical source is app.py)
ACCENT_COLOR = "#FF9500"
BG_DARK = "#1e1e1e"
BG_CARD = "#2d2d2d"
TEXT_PRIMARY = "#ffffff"
TEXT_SECONDARY = "#999999"
SUCCESS_COLOR = "#4CAF50"
ERROR_COLOR = "#f44336"


class MainWindow(QMainWindow):
    """Fixed-size main window hosting the drop-zone and radial menu."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Elumichai")
        self.setFixedSize(QSize(500, 550))
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        # State --------------------------------------------------------------
        self._always_on_top = False
        self._worker: ConversionWorker | None = None

        # Central widget -----------------------------------------------------
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)

        self.drop_zone = DropZone(self)
        self.drop_zone.files_dropped.connect(self._on_files_dropped)
        self.drop_zone.hold_ready.connect(self._on_files_dropped)
        self.drop_zone.drag_mode_requested.connect(self._on_drag_mode_requested)
        layout.addWidget(self.drop_zone)

        self.setCentralWidget(central)

        # Radial menu (overlay — initially hidden) ---------------------------
        self.radial_menu = RadialMenu(self)
        self.radial_menu.conversion_requested.connect(self._start_conversion)
        self.radial_menu.tool_requested.connect(self._start_tool)
        self.radial_menu.action_requested.connect(self._run_action)
        try:
            from citrus_converter.config import Config
            self.radial_menu.set_sound_enabled(Config().get("navigation_sound", True))
        except Exception:
            pass
        self.radial_menu.hide()

        # Menu bar -----------------------------------------------------------
        self._build_menus()

        # Status bar ---------------------------------------------------------
        self.status = QStatusBar(self)
        self.setStatusBar(self.status)
        self.status.showMessage("Ready — drop files to convert")

    # === Menu bar =========================================================
    def _build_menus(self) -> None:
        menu_bar = self.menuBar()

        # -- File menu -------------------------------------------------------
        file_menu = menu_bar.addMenu("&File")

        settings_act = QAction("&Settings…", self)
        settings_act.setShortcut(QKeySequence("Ctrl+,"))
        settings_act.triggered.connect(self._open_settings)
        file_menu.addAction(settings_act)

        on_top_act = QAction("Always on &Top", self)
        on_top_act.setCheckable(True)
        on_top_act.toggled.connect(self._toggle_on_top)
        file_menu.addAction(on_top_act)

        file_menu.addSeparator()

        quit_act = QAction("&Quit", self)
        quit_act.setShortcut(QKeySequence.Quit)
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        # -- Help menu -------------------------------------------------------
        help_menu = menu_bar.addMenu("&Help")

        about_act = QAction("&About Elumichai", self)
        about_act.triggered.connect(self._show_about)
        help_menu.addAction(about_act)

        shortcuts_act = QAction("&Keyboard Shortcuts", self)
        shortcuts_act.setShortcut(QKeySequence("Ctrl+/"))
        shortcuts_act.triggered.connect(self._show_shortcuts)
        help_menu.addAction(shortcuts_act)

    # === Slot handlers ====================================================
    def _on_files_dropped(self, file_paths: list) -> None:
        """Called when files are dropped onto the DropZone."""
        if not file_paths:
            return

        self.status.showMessage(f"{len(file_paths)} file(s) received")

        # Determine available conversions using the formats module
        try:
            from citrus_converter.formats import (
                get_conversions_for_file,
                get_tools_for_file,
            )
            conversions = get_conversions_for_file(file_paths[0])
            tools = get_tools_for_file(file_paths[0])
        except Exception:
            conversions = []
            tools = []

        if not conversions:
            conversions = ["png", "jpg", "webp", "pdf", "mp4", "mp3", "docx", "zip"]
        if not tools:
            tools = ["compress", "edit_metadata", "crop_images", "trim_video", "merge_pdfs"]

        self.radial_menu.show_for_files(file_paths, conversions, tools)

    def present_files(self, file_paths: list[str]) -> None:
        """Show the cursor wheel for files supplied to the background app."""
        self._on_files_dropped([path for path in file_paths if os.path.exists(path)])

    def _on_drag_mode_requested(self, file_paths: list[str], mode: str) -> None:
        """Open the wheel as soon as a drag modifier is pressed."""
        if not file_paths:
            return
        try:
            from citrus_converter.formats import get_conversions_for_file, get_tools_for_file
            conversions = get_conversions_for_file(file_paths[0])
            tools = get_tools_for_file(file_paths[0])
        except Exception:
            conversions = []
            tools = []

        if not conversions:
            conversions = ["png", "jpg", "webp", "pdf", "mp4", "mp3", "docx", "zip"]
        if not tools:
            tools = ["compress", "edit_metadata", "crop_images", "trim_video", "merge_pdfs"]

        self.radial_menu.show_for_files(file_paths, conversions, tools, wheel=mode)

    def _start_conversion(self, file_paths: list, target_format: str) -> None:
        """Kick off a background conversion."""
        self.status.showMessage(f"Converting to {target_format.upper()}…")

        # Determine output directory
        try:
            from citrus_converter.config import Config
            cfg = Config()
            output_mode = cfg.get("output_location", "same")
            if output_mode == "same":
                output_dir = os.path.dirname(file_paths[0])
            elif output_mode == "custom":
                output_dir = cfg.get("output_custom_path", os.path.dirname(file_paths[0]))
            else:
                output_dir = None  # ask — handled downstream
        except Exception:
            output_dir = os.path.dirname(file_paths[0])

        self._worker = ConversionWorker(file_paths, target_format, output_dir)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, pct: int) -> None:
        self.status.showMessage(f"Converting… {pct}%")

    def _on_finished(self, result: str) -> None:
        self.status.showMessage(f"✓ {result}")
        self.drop_zone.show_success()
        # Notification via tray
        try:
            from citrus_converter.config import Config
            if Config().get("notifications", True):
                tray = getattr(self.parent(), "tray", None)
                if tray is None:
                    from PySide6.QtWidgets import QApplication
                    app = QApplication.instance()
                    tray = getattr(app, "tray", None)
                if tray:
                    tray.showMessage("Elumichai", result)
        except Exception:
            pass

    def _on_error(self, msg: str) -> None:
        self.status.showMessage(f"✗ Error: {msg}")
        self.drop_zone.show_error()

    def _start_tool(self, file_paths: list, tool_name: str) -> None:
        """Run an existing local tool, or explain when a richer editor is needed."""
        if not file_paths:
            return
        path = file_paths[0]
        category = None
        try:
            from citrus_converter.formats import get_category
            category = get_category(path)
            from citrus_converter.tools import get_tool
            tool = get_tool(category)
            aliases = {
                "trim_video": "trim", "change_video_speed": "change_speed",
                "save_video_frames": "snapshot", "normalize_volume": "normalize",
                "trim_audio": "trim", "convert_audio_channels": "change_channels",
                "edit_metadata": "read_metadata", "crop_images": "crop",
            }
            method_name = aliases.get(tool_name, tool_name)
            method = getattr(tool, method_name, None) if tool else None
            if method is None:
                QMessageBox.information(
                    self, "Elumichai tool", f"{tool_name.replace('_', ' ').title()} is available in the wheel, but this operation needs a parameter editor before it can run on Linux."
                )
                return
            if method_name == "read_metadata":
                result = method(path)
                text = "\n".join(f"{key}: {value}" for key, value in list(result.items())[:30])
                QMessageBox.information(self, "Metadata", text or "No metadata found.")
                return

            kwargs = {}
            if method_name == "compress":
                value, ok = QInputDialog.getInt(self, "Compress", "Quality / CRF (1–100):", 75, 1, 100)
                if not ok:
                    return
                kwargs["quality" if category == "image" else "crf"] = value
            elif method_name in {"trim", "trim_video", "trim_audio"}:
                start, ok = QInputDialog.getText(self, "Trim", "Start time (seconds or HH:MM:SS):")
                if not ok:
                    return
                end, ok = QInputDialog.getText(self, "Trim", "End time (seconds or HH:MM:SS):")
                if not ok:
                    return
                kwargs.update(start=start, end=end)
            elif method_name == "crop":
                values = []
                for label in ("X", "Y", "Width", "Height"):
                    value, ok = QInputDialog.getInt(self, "Crop", f"{label}:", 0, 0, 100000)
                    if not ok:
                        return
                    values.append(value)
                kwargs.update(zip(("x", "y", "w", "h"), values))
            elif method_name == "change_speed":
                value, ok = QInputDialog.getDouble(self, "Change speed", "Playback factor:", 1.0, 0.1, 10.0, 2)
                if not ok:
                    return
                kwargs["factor"] = value
            elif method_name == "snapshot":
                value, ok = QInputDialog.getText(self, "Save video frame", "Timestamp:")
                if not ok:
                    return
                kwargs["timestamp"] = value
            elif method_name == "change_channels":
                value, ok = QInputDialog.getInt(self, "Audio channels", "Channels (1 or 2):", 2, 1, 2)
                if not ok:
                    return
                kwargs["channels"] = value

            result = method(path, **kwargs)
            QMessageBox.information(self, "Elumichai tool", f"Finished:\n{result}")
        except Exception as exc:
            QMessageBox.warning(self, "Tool unavailable", str(exc))

    def _run_action(self, file_paths: list, action: str) -> None:
        """Implement the six file actions with Linux-native equivalents."""
        if not file_paths:
            return
        from PySide6.QtWidgets import QApplication
        if action == "copy_path":
            QApplication.clipboard().setText("\n".join(file_paths))
        elif action == "copy":
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(path) for path in file_paths])
            QApplication.clipboard().setMimeData(mime)
        elif action == "move":
            destination = QFileDialog.getExistingDirectory(self, "Move files to…")
            if destination:
                for path in file_paths:
                    shutil.move(path, os.path.join(destination, os.path.basename(path)))
        elif action == "terminal":
            folder = os.path.dirname(file_paths[0])
            for command in (("x-terminal-emulator", "--working-directory", folder), ("gnome-terminal", "--working-directory", folder)):
                if shutil.which(command[0]):
                    subprocess.Popen(command)
                    break
        elif action == "float":
            QMessageBox.information(self, "Float", "A floating shelf is not provided by the Linux desktop, but you can keep Elumichai's tray icon available while moving files.")
        elif action == "airdrop":
            QMessageBox.information(self, "AirDrop", "AirDrop is Apple-only. Use your desktop's share action for these files.")

    # -- Dialogs -----------------------------------------------------------
    def _open_settings(self) -> None:
        dlg = SettingsDialog(self)
        if dlg.exec():
            # Re-apply theme if changed
            try:
                from citrus_converter.config import Config
                app = self.parent()
                if app is None:
                    from PySide6.QtWidgets import QApplication
                    app = QApplication.instance()
                if hasattr(app, "apply_theme"):
                    app.apply_theme(Config().get("theme", "dark"))
            except Exception:
                pass

    def _show_about(self) -> None:
        AboutDialog(self).exec()

    def _show_shortcuts(self) -> None:
        QMessageBox.information(
            self,
            "Keyboard Shortcuts",
            (
                "<table cellpadding='4'>"
                "<tr><td><b>Ctrl+,</b></td><td>Settings</td></tr>"
                "<tr><td><b>Ctrl+/</b></td><td>Show shortcuts</td></tr>"
                "<tr><td><b>Ctrl+Q</b></td><td>Quit</td></tr>"
                "<tr><td><b>Escape</b></td><td>Dismiss radial menu</td></tr>"
                "</table>"
            ),
        )

    def _toggle_on_top(self, checked: bool) -> None:
        self._always_on_top = checked
        flags = self.windowFlags()
        if checked:
            self.setWindowFlags(flags | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(flags & ~Qt.WindowStaysOnTopHint)
        self.show()  # re-show after flag change

    # === Overrides ========================================================
    def closeEvent(self, event) -> None:  # noqa: N802
        """Cancel any running worker on close."""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2000)
        super().closeEvent(event)
