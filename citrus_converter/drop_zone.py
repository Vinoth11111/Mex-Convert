"""
Elumichai — Drop Zone Widget
=====================================
Large drag-and-drop area that accepts files from the file manager,
highlights on hover, and emits the list of dropped file paths.
"""

import os
from urllib.parse import unquote
from pathlib import Path

from PySide6.QtCore import (
    Qt,
    QPropertyAnimation,
    QEasingCurve,
    Signal,
    Property,
    QMimeDatabase,
    QTimer,
)
from PySide6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QFont,
    QBrush,
    QPainterPath,
    QLinearGradient,
)
from PySide6.QtWidgets import QWidget

# Colour tokens
ACCENT_COLOR = QColor("#FF9500")
BG_CARD = QColor("#2d2d2d")
TEXT_PRIMARY = QColor("#ffffff")
TEXT_SECONDARY = QColor("#999999")
SUCCESS_COLOR = QColor("#4CAF50")
ERROR_COLOR = QColor("#f44336")

_MIME_DB = QMimeDatabase()


class DropZone(QWidget):
    """
    File drop zone with animated dashed border and drag-over glow.

    Signals
    -------
    files_dropped(list[str])
        Emitted with the list of local file paths when files are dropped.
    """

    files_dropped = Signal(list)
    hold_ready = Signal(list)
    drag_mode_requested = Signal(list, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumSize(460, 460)

        # internal state
        self._dragging = False
        self._glow_opacity: float = 0.0
        self._status: str = "idle"  # idle | success | error
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._reset_status)
        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.setInterval(3000)
        self._hold_timer.timeout.connect(self._on_hold_ready)
        self._hold_paths: list[str] = []
        self._hold_ready = False
        self._drag_mode: str | None = None

        # glow animation
        self._glow_anim = QPropertyAnimation(self, b"glowOpacity")
        self._glow_anim.setDuration(250)
        self._glow_anim.setEasingCurve(QEasingCurve.InOutQuad)

    # === Custom property for animation ====================================
    @Property(float)
    def glowOpacity(self) -> float:  # noqa: N802
        return self._glow_opacity

    @glowOpacity.setter
    def glowOpacity(self, val: float) -> None:  # noqa: N802
        self._glow_opacity = val
        self.update()

    # === Public helpers ===================================================
    def show_success(self) -> None:
        self._status = "success"
        self.update()
        self._status_timer.start(2500)

    def show_error(self) -> None:
        self._status = "error"
        self.update()
        self._status_timer.start(3000)

    def _reset_status(self) -> None:
        self._status = "idle"
        self.update()

    # === Drag-and-drop events =============================================
    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls() or event.mimeData().hasFormat("text/uri-list"):
            event.acceptProposedAction()
            self._dragging = True
            self._hold_paths = self._paths_from_mime(event.mimeData())
            self._hold_ready = False
            self._drag_mode = None
            self._hold_timer.start()
            self._update_drag_mode(event.keyboardModifiers())
            self._animate_glow(1.0)
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        self._update_drag_mode(event.keyboardModifiers())
        event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._dragging = False
        self._hold_timer.stop()
        self._hold_paths = []
        self._hold_ready = False
        self._drag_mode = None
        self._animate_glow(0.0)
        event.accept()

    def dropEvent(self, event) -> None:  # noqa: N802
        self._dragging = False
        self._hold_timer.stop()
        self._drag_mode = None
        self._animate_glow(0.0)

        paths = self._paths_from_mime(event.mimeData())

        if paths:
            event.acceptProposedAction()
            self.files_dropped.emit(paths)
        else:
            event.ignore()

    def _paths_from_mime(self, mime) -> list[str]:
        paths: list[str] = []
        if mime.hasUrls():
            for url in mime.urls():
                local = url.toLocalFile()
                if not local and url.scheme() == "file":
                    local = unquote(url.path())
                if local and os.path.exists(local):
                    paths.append(local)
        if not paths and mime.hasFormat("text/uri-list"):
            raw = bytes(mime.data("text/uri-list")).decode("utf-8", errors="ignore")
            for line in raw.splitlines():
                line = line.strip()
                if line.startswith("file://"):
                    path = unquote(line[7:])
                    if os.path.exists(path):
                        paths.append(path)
        return paths

    def _on_hold_ready(self) -> None:
        """Open the wheel after a deliberate three-second file hold."""
        if self._dragging and self._hold_paths and not self._hold_ready:
            self._hold_ready = True
            self.hold_ready.emit(self._hold_paths)

    def _update_drag_mode(self, modifiers) -> None:
        """Map Tangerine-style drag modifiers to Linux keyboard modifiers.

        Shift is the conversion wheel. Linux Fn keys normally do not emit a
        desktop-visible modifier, so Ctrl/Meta are accepted as practical Fn
        equivalents for the tools wheel. Alt is left free for file-manager
        drag operations.
        """
        if not self._hold_paths:
            return
        from PySide6.QtCore import Qt
        if modifiers & Qt.ShiftModifier:
            mode = "formats"
        elif modifiers & (Qt.ControlModifier | Qt.MetaModifier):
            mode = "tools"
        else:
            mode = None
        if mode and mode != self._drag_mode:
            self._drag_mode = mode
            self.drag_mode_requested.emit(self._hold_paths, mode)

    # === Painting =========================================================
    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        margin = 16
        rect = self.rect().adjusted(margin, margin, -margin, -margin)
        radius = 20.0

        # --- Background rounded rect ---
        bg = QPainterPath()
        bg.addRoundedRect(float(rect.x()), float(rect.y()),
                          float(rect.width()), float(rect.height()),
                          radius, radius)
        p.fillPath(bg, QBrush(BG_CARD))

        # --- Glow ring on drag-over ---
        if self._glow_opacity > 0.01:
            glow_color = QColor(ACCENT_COLOR)
            glow_color.setAlphaF(self._glow_opacity * 0.35)
            glow_pen = QPen(glow_color, 4)
            p.setPen(glow_pen)
            p.drawRoundedRect(rect.adjusted(-2, -2, 2, 2), radius + 2, radius + 2)

        # --- Dashed border ---
        border_color = QColor(ACCENT_COLOR) if self._dragging else QColor(TEXT_SECONDARY)
        if self._status == "success":
            border_color = QColor(SUCCESS_COLOR)
        elif self._status == "error":
            border_color = QColor(ERROR_COLOR)
        border_color.setAlphaF(0.7 if not self._dragging else 1.0)

        pen = QPen(border_color, 2.5, Qt.DashLine)
        pen.setDashPattern([8, 6])
        p.setPen(pen)
        p.drawRoundedRect(rect, radius, radius)

        # --- Icon ---
        icon_size = 48
        cx = w // 2
        cy = h // 2 - 30

        # draw a simple down-arrow + box icon
        p.setPen(QPen(ACCENT_COLOR if self._dragging else TEXT_SECONDARY, 3,
                       Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        # arrow shaft
        p.drawLine(cx, cy - 20, cx, cy + 10)
        # arrow head
        p.drawLine(cx - 10, cy, cx, cy + 10)
        p.drawLine(cx + 10, cy, cx, cy + 10)
        # tray
        p.drawLine(cx - 22, cy + 10, cx - 22, cy + 22)
        p.drawLine(cx - 22, cy + 22, cx + 22, cy + 22)
        p.drawLine(cx + 22, cy + 22, cx + 22, cy + 10)

        # --- Text ---
        if self._status == "success":
            label = "✓ Conversion complete!"
            sub_label = "Drop more files to continue"
            label_color = SUCCESS_COLOR
        elif self._status == "error":
            label = "✗ Conversion failed"
            sub_label = "Check the status bar for details"
            label_color = ERROR_COLOR
        elif self._dragging:
            label = "Release to convert"
            sub_label = ""
            label_color = ACCENT_COLOR
        else:
            label = "Drop files here to convert"
            sub_label = "Images · Videos · Audio · Documents"
            label_color = TEXT_PRIMARY

        p.setPen(QPen(label_color))
        font = QFont("Sans", 15, QFont.DemiBold)
        p.setFont(font)
        p.drawText(self.rect().adjusted(0, 40, 0, 0), Qt.AlignHCenter | Qt.AlignCenter, label)

        if sub_label:
            p.setPen(QPen(TEXT_SECONDARY))
            sub_font = QFont("Sans", 10)
            p.setFont(sub_font)
            p.drawText(self.rect().adjusted(0, 80, 0, 0), Qt.AlignHCenter | Qt.AlignCenter, sub_label)

        p.end()

    # === Animation helper =================================================
    def _animate_glow(self, target: float) -> None:
        self._glow_anim.stop()
        self._glow_anim.setStartValue(self._glow_opacity)
        self._glow_anim.setEndValue(target)
        self._glow_anim.start()
