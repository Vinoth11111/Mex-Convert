"""
Elumichai — Radial Menu
=================================
A beautiful circular popup that shows conversion target formats as
QPainter-drawn arc segments around a centre file-info label.

Two rings are available:
  • **Formats** — target output formats (e.g. PNG, WebP, PDF)
  • **Tools**   — operations like compress, resize, trim
Toggle between them with a small button at the bottom.
"""

from __future__ import annotations

import math
import os
from typing import List, Optional
from urllib.parse import unquote

from PySide6.QtCore import (
    Qt,
    QPointF,
    QPoint,
    QRectF,
    QRect,
    QPropertyAnimation,
    QEasingCurve,
    Signal,
    Property,
    QTimer,
    QUrl,
)
from PySide6.QtGui import (
    QPainter,
    QPainterPath,
    QColor,
    QFont,
    QPen,
    QBrush,
    QFontMetrics,
    QRadialGradient,
    QCursor,
)
from PySide6.QtWidgets import QWidget, QApplication

# Colour tokens
ACCENT = QColor("#FF9500")
ACCENT_HOVER = QColor("#FFb340")
BG_OVERLAY = QColor(30, 30, 30, 220)
BG_SEGMENT = QColor("#2d2d2d")
BG_SEGMENT_HOVER = QColor("#3a3a3a")
TEXT_WHITE = QColor("#ffffff")
TEXT_GREY = QColor("#999999")
GAP_DEG = 3.0  # gap between arc segments in degrees

# Default fallbacks so the radial menu never renders an empty ring without text
DEFAULT_FORMATS = ["png", "jpg", "webp", "pdf", "mp4", "mp3", "docx", "zip"]
DEFAULT_TOOLS = ["compress", "edit_metadata", "crop_images", "trim_video", "merge_pdfs"]

TOOL_DISPLAY_NAMES = {
    "compress": "COMPRESS",
    "edit_metadata": "METADATA",
    "edit_photos": "EDIT",
    "annotate_photos": "ANNOTATE",
    "add_background": "BACKGROUND",
    "crop_images": "CROP",
    "crop_video": "CROP",
    "redact_photos": "REDACT",
    "redact_video": "REDACT",
    "create_pdf": "PDF",
    "create_collage": "COLLAGE",
    "trim_video": "TRIM",
    "trim_audio": "TRIM",
    "change_video_speed": "SPEED",
    "join_videos": "JOIN",
    "save_video_frames": "FRAMES",
    "split_video": "SPLIT",
    "normalize_volume": "NORMALIZE",
    "create_audio_visualizer": "VISUALIZER",
    "convert_audio_channels": "CHANNELS",
    "bleep_audio": "BLEEP",
    "merge_pdfs": "MERGE",
    "organize_pdf_pages": "ORGANIZE",
    "airdrop": "AIRDROP",
    "float": "FLOAT",
    "copy": "COPY",
    "move": "MOVE",
    "copy_path": "COPY PATH",
    "terminal": "TERMINAL",
}


def _available_screen_geometry(global_pos: QPoint) -> QRect:
    """Return the available geometry for the screen containing a point."""
    screen = QApplication.screenAt(global_pos) or QApplication.primaryScreen()
    if screen is not None:
        return screen.availableGeometry()
    return QRect(0, 0, 1920, 1080)


class RadialMenu(QWidget):
    """Popup radial/pie menu for choosing conversion targets.

    Signals
    -------
    conversion_requested(list[str], str)
        Emitted with (file_paths, target_format) when the user picks a format.
    tool_requested(list[str], str)
        Emitted with (file_paths, tool_name) when the user picks a tool.
    """

    conversion_requested = Signal(list, str)
    tool_requested = Signal(list, str)
    action_requested = Signal(list, str)

    # Ring radius parameters (relative to widget size)
    _INNER_RADIUS_RATIO = 0.22
    _OUTER_RADIUS_RATIO = 0.44
    _CENTRE_RADIUS_RATIO = 0.18

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(None)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        # data
        self._file_paths: list[str] = []
        self._format_items: list[str] = list(DEFAULT_FORMATS)
        self._tool_items: list[str] = list(DEFAULT_TOOLS)
        self._wheel = "formats"  # formats → tools → actions
        self._sound_enabled = True
        self._global_mode = False
        self._global_cursor = QPoint(0, 0)

        # interaction state
        self._hovered_index: int = -1
        self._hovered_center: bool = False
        self._popup_opacity: float = 0.0

        # fade animation
        self._fade_anim = QPropertyAnimation(self, b"popupOpacity")
        self._fade_anim.setDuration(200)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)

    # === animated opacity property ========================================
    @Property(float)
    def popupOpacity(self) -> float:  # noqa: N802
        return self._popup_opacity

    @popupOpacity.setter
    def popupOpacity(self, v: float) -> None:  # noqa: N802
        self._popup_opacity = v
        self.update()
        if v <= 0.01 and not self._fade_anim.state():
            self.hide()

    # === public API =======================================================
    def show_for_files(
        self,
        file_paths: list[str],
        conversions: list[str],
        tools: list[str],
        wheel: str = "formats",
    ) -> None:
        """Populate the menu and display it centred on the parent."""
        self._global_mode = False
        self._file_paths = file_paths
        self._format_items = (conversions if conversions else list(DEFAULT_FORMATS))[:12]
        self._tool_items = (tools if tools else list(DEFAULT_TOOLS))[:12]
        self._wheel = wheel if wheel in {"formats", "tools", "actions"} else "formats"
        self._hovered_index = -1
        self._hovered_center = False

        self.resize(520, 520)
        cursor = QCursor.pos()
        screen = _available_screen_geometry(cursor)
        x = max(screen.left(), min(cursor.x() - self.width() // 2, screen.right() - self.width()))
        y = max(screen.top(), min(cursor.y() - self.height() // 2, screen.bottom() - self.height()))
        self.move(x, y)

        self.show()
        self.raise_()
        self.setFocus()

        # fade-in
        self._fade_anim.stop()
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()

    def set_wheel(self, wheel: str) -> None:
        if wheel in {"formats", "tools", "actions"}:
            self._wheel = wheel
            self._hovered_index = -1
            self._hovered_center = False
            self.update()

    def set_sound_enabled(self, enabled: bool) -> None:
        self._sound_enabled = enabled

    def show_global(self, wheel: str, global_pos: QPoint) -> None:
        """Show a transparent full-screen Xdnd target under the dragged file."""
        self._global_mode = True
        self._global_cursor = global_pos
        self._file_paths = []
        self._format_items = list(DEFAULT_FORMATS)
        self._tool_items = list(DEFAULT_TOOLS)
        self._wheel = wheel if wheel in {"formats", "tools"} else "formats"
        self._hovered_index = -1
        self._hovered_center = False
        # A global overlay is shown directly while a drag is in progress.
        # It does not use the normal fade-in path, so explicitly make it
        # visible. Leaving this at the constructor default (0.0) makes
        # paintEvent() return without drawing anything.
        self._fade_anim.stop()
        self._popup_opacity = 1.0
        geometry = _available_screen_geometry(global_pos)
        self.setGeometry(geometry)
        self.show()
        self.raise_()
        self.update()

    def update_global_cursor(self, global_pos: QPoint) -> None:
        """Update hover state while keeping the ring fixed in place.

        The ring is anchored at the point where the modifier-drag becomes
        active. The dragged pointer is then allowed to move across that
        stationary ring to choose a segment; moving the pointer must not move
        the target itself.
        """
        if self._global_mode:
            local_pos = QPointF(global_pos.x() - self.x(), global_pos.y() - self.y())
            idx = self._index_at(local_pos, allow_outside=True)
            c = self._centre()
            inner_r, _, _ = self._radii()
            center_hovered = math.hypot(local_pos.x() - c.x(), local_pos.y() - c.y()) < inner_r
            state_changed = (idx != self._hovered_index) or (center_hovered != self._hovered_center)
            self._hovered_index = idx
            self._hovered_center = center_hovered
            if idx >= 0 and state_changed:
                self._play_hover_sound()
            if state_changed:
                self.update()

    def dismiss(self) -> None:
        """Fade out and hide."""
        self._hovered_center = False
        self._fade_anim.stop()
        self._fade_anim.setStartValue(self._popup_opacity)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.finished.connect(self.hide)
        self._fade_anim.start()

    # === property helpers =================================================
    @property
    def _items(self) -> list[str]:
        if self._wheel == "tools":
            return self._tool_items if self._tool_items else list(DEFAULT_TOOLS)
        if self._wheel == "actions":
            return ["airdrop", "float", "copy", "move", "copy_path", "terminal"]
        return self._format_items if self._format_items else list(DEFAULT_FORMATS)

    def _extract_paths_from_mime(self, mime) -> list[str]:
        """Safely extract local filesystem paths from MIME payload."""
        paths: list[str] = []
        if mime.hasUrls():
            for url in mime.urls():
                p = url.toLocalFile()
                if not p and url.scheme() == "file":
                    p = unquote(url.path())
                if p:
                    paths.append(p)
        if not paths and mime.hasFormat("text/uri-list"):
            raw = bytes(mime.data("text/uri-list")).decode("utf-8", errors="ignore")
            for line in raw.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                p = QUrl(line).toLocalFile()
                if not p and line.startswith("file://"):
                    p = unquote(line[7:])
                if p:
                    paths.append(p)
        if not paths and mime.hasText():
            raw = mime.text().strip()
            for line in raw.splitlines():
                line = line.strip()
                if line.startswith("file://"):
                    p = QUrl(line).toLocalFile() or unquote(line[7:])
                    if p:
                        paths.append(p)
                elif line.startswith("/") and os.path.exists(line):
                    paths.append(line)
        return paths

    def _update_for_paths(self, paths: list[str]) -> None:
        """Update items based on detected file paths."""
        if not paths:
            return
        self._file_paths = paths
        try:
            from citrus_converter.formats import get_conversions_for_file, get_tools_for_file
            conversions = get_conversions_for_file(paths[0])
            tools = get_tools_for_file(paths[0])
            self._format_items = conversions[:12] if conversions else list(DEFAULT_FORMATS)
            self._tool_items = tools[:12] if tools else list(DEFAULT_TOOLS)
        except Exception:
            self._format_items = list(DEFAULT_FORMATS)
            self._tool_items = list(DEFAULT_TOOLS)
        self.update()

    # === geometry helpers =================================================
    def _centre(self) -> QPointF:
        if self._global_mode:
            return QPointF(
                self._global_cursor.x() - self.x(),
                self._global_cursor.y() - self.y(),
            )
        return QPointF(self.width() / 2, self.height() / 2 - 10)

    def _radii(self) -> tuple[float, float, float]:
        """Return (inner_r, outer_r, centre_r) in pixels."""
        if self._global_mode:
            return (72.0, 150.0, 52.0)
        half = min(self.width(), self.height()) / 2
        return (
            half * self._INNER_RADIUS_RATIO,
            half * self._OUTER_RADIUS_RATIO,
            half * self._CENTRE_RADIUS_RATIO,
        )

    def _segment_angles(self, count: int) -> list[tuple[float, float]]:
        """Return (start_angle, span_angle) pairs in degrees for *count* segments."""
        if count == 0:
            return []
        span = (360.0 - count * GAP_DEG) / count
        angles: list[tuple[float, float]] = []
        start = 90.0  # top-centre
        for _ in range(count):
            angles.append((start, span))
            start += span + GAP_DEG
        return angles

    # === hit testing ======================================================
    def _index_at(self, pos: QPointF, allow_outside: bool = False) -> int:
        """Return the segment for a point, or -1 when it is not selectable.

        In global drag mode, selection is based on the point's angle around
        the anchored ring. This keeps a format selected even when the
        dragged file is outside the ring's visible radius.
        """
        c = self._centre()
        dx = pos.x() - c.x()
        dy = pos.y() - c.y()
        dist = math.hypot(dx, dy)
        inner_r, outer_r, _ = self._radii()
        items = self._items
        if not items:
            return -1
        # Inside the center/middle hole of the ring: always unselected (cancel zone)
        if dist < inner_r:
            return -1
        if not allow_outside and dist > outer_r + 6:
            return -1

        # angle in degrees (0 = 3-o'clock, CCW positive — match Qt convention)
        angle_rad = math.atan2(-dy, dx)
        angle_deg = math.degrees(angle_rad) % 360

        angles = self._segment_angles(len(items))
        nearest_index = -1
        nearest_distance = 360.0
        for i, (start, span) in enumerate(angles):
            # normalise start to 0-360
            s = start % 360
            e = (start + span) % 360
            if s < e:
                if s <= angle_deg <= e:
                    return i
            else:  # wraps around 0
                if angle_deg >= s or angle_deg <= e:
                    return i
            midpoint = (start + span / 2.0) % 360
            distance = abs(angle_deg - midpoint)
            distance = min(distance, 360.0 - distance)
            if distance < nearest_distance:
                nearest_distance = distance
                nearest_index = i
        return nearest_index if allow_outside else -1

    # === toggle button rect ===============================================
    def _toggle_rect(self) -> QRectF:
        c = self._centre()
        _, outer_r, _ = self._radii()
        bw, bh = 80, 26
        return QRectF(c.x() - bw / 2, c.y() + outer_r + 18, bw, bh)

    # === event overrides ==================================================
    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self.dismiss()
        else:
            super().keyPressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = QPointF(event.pos())
        idx = self._index_at(pos, allow_outside=self._global_mode)
        c = self._centre()
        inner_r, _, _ = self._radii()
        center_hovered = math.hypot(pos.x() - c.x(), pos.y() - c.y()) < inner_r
        state_changed = (idx != self._hovered_index) or (center_hovered != self._hovered_center)
        self._hovered_index = idx
        self._hovered_center = center_hovered
        if idx >= 0 and state_changed:
            self._play_hover_sound()
        if state_changed:
            self.update()

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        event.setDropAction(Qt.CopyAction)
        paths = self._extract_paths_from_mime(event.mimeData())
        if paths:
            self._update_for_paths(paths)
        else:
            self.update()
        event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        event.setDropAction(Qt.CopyAction)
        if not self._file_paths:
            paths = self._extract_paths_from_mime(event.mimeData())
            if paths:
                self._update_for_paths(paths)
        pos = QPointF(event.pos())
        self._hovered_index = self._index_at(
            pos, allow_outside=self._global_mode
        )
        c = self._centre()
        inner_r, _, _ = self._radii()
        self._hovered_center = math.hypot(pos.x() - c.x(), pos.y() - c.y()) < inner_r
        self.update()
        event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        """Choose the segment where the held file is released, or cancel if in the center."""
        if not self._file_paths:
            paths = self._extract_paths_from_mime(event.mimeData())
            if paths:
                self._update_for_paths(paths)

        pos = QPointF(event.pos())
        idx = self._index_at(pos, allow_outside=self._global_mode)
        c = self._centre()
        inner_r, _, _ = self._radii()
        dist = math.hypot(pos.x() - c.x(), pos.y() - c.y())

        if dist < inner_r:
            # Dropped inside the mid/center of the ring: cancel the operation
            self.dismiss()
            event.acceptProposedAction()
            return

        if idx >= 0:
            picked = self._items[idx]
            self.dismiss()
            if self._wheel == "tools":
                self.tool_requested.emit(self._file_paths, picked)
            elif self._wheel == "actions":
                self.action_requested.emit(self._file_paths, picked)
            else:
                self.conversion_requested.emit(self._file_paths, picked)
            event.acceptProposedAction()
        else:
            self.dismiss()
            event.ignore()

    def _play_hover_sound(self) -> None:
        if self._sound_enabled:
            QApplication.beep()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton:
            return

        pos = QPointF(event.pos())

        # Check toggle button
        if self._toggle_rect().contains(pos):
            self._wheel = {"formats": "tools", "tools": "actions", "actions": "formats"}[self._wheel]
            self._hovered_index = -1
            self._hovered_center = False
            self._play_hover_sound()
            self.update()
            return

        # Clicking inside the center of the ring: cancel and dismiss
        c = self._centre()
        inner_r, outer_r, _ = self._radii()
        dist = math.hypot(pos.x() - c.x(), pos.y() - c.y())
        if dist < inner_r:
            self.dismiss()
            return

        # Check segment
        idx = self._index_at(pos)
        if idx >= 0:
            items = self._items
            picked = items[idx]
            self.dismiss()
            if self._wheel == "tools":
                self.tool_requested.emit(self._file_paths, picked)
            elif self._wheel == "actions":
                self.action_requested.emit(self._file_paths, picked)
            else:
                self.conversion_requested.emit(self._file_paths, picked)
            return

        # Click outside — dismiss
        if dist > outer_r + 30:
            self.dismiss()

    # === painting =========================================================
    def paintEvent(self, event) -> None:  # noqa: N802
        if self._popup_opacity < 0.01:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setOpacity(self._popup_opacity)

        w, h = self.width(), self.height()
        c = self._centre()
        inner_r, outer_r, centre_r = self._radii()
        items = self._items
        angles = self._segment_angles(len(items))

        # 1) Keep the window transparent so this looks like a ring around the
        # file/cursor rather than another small dark application window.
        glow = QRadialGradient(c, outer_r + 30)
        glow.setColorAt(0.0, QColor(255, 149, 0, 30))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(glow))
        p.setPen(Qt.NoPen)
        p.drawEllipse(c, outer_r + 30, outer_r + 30)

        # 2) Draw arc segments
        for i, (start_deg, span_deg) in enumerate(angles):
            hovered = i == self._hovered_index
            self._draw_segment(p, c, inner_r, outer_r, start_deg, span_deg,
                               items[i], hovered)

        # 3) Centre circle — file info & cancel state
        self._draw_centre(p, c, centre_r)

        # 4) Toggle button (Formats / Tools)
        self._draw_toggle(p)

        p.end()

    def _draw_segment(
        self,
        p: QPainter,
        c: QPointF,
        inner_r: float,
        outer_r: float,
        start_deg: float,
        span_deg: float,
        label: str,
        hovered: bool,
    ) -> None:
        """Draw a single arc segment with label."""
        # Build the arc path
        grow = 6 if hovered else 0
        o_r = outer_r + grow
        i_r = inner_r - (grow * 0.3)

        outer_rect = QRectF(c.x() - o_r, c.y() - o_r, o_r * 2, o_r * 2)
        inner_rect = QRectF(c.x() - i_r, c.y() - i_r, i_r * 2, i_r * 2)

        path = QPainterPath()
        path.arcMoveTo(outer_rect, start_deg)
        path.arcTo(outer_rect, start_deg, span_deg)
        path.arcTo(inner_rect, start_deg + span_deg, -span_deg)
        path.closeSubpath()

        # fill
        if hovered:
            fill_color = ACCENT
        else:
            fill_color = BG_SEGMENT

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(fill_color))
        p.drawPath(path)

        # Subtle border
        border = QColor("#444") if not hovered else QColor("#FFb340")
        p.setPen(QPen(border, 1.0))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

        # Label text — positioned at the midpoint of the segment arc
        mid_angle_deg = start_deg + span_deg / 2
        mid_r = (inner_r + o_r) / 2
        rad = math.radians(mid_angle_deg)
        tx = c.x() + mid_r * math.cos(rad)
        ty = c.y() - mid_r * math.sin(rad)

        font = QFont("Sans", 10, QFont.Bold)
        p.setFont(font)
        p.setPen(QPen(TEXT_WHITE if not hovered else QColor("#1e1e1e")))

        display = TOOL_DISPLAY_NAMES.get(label, label.replace("_", " ").upper())
        fm = QFontMetrics(font)
        max_width = int((o_r - inner_r) * 1.5)
        if fm.horizontalAdvance(display) > max_width:
            display = fm.elidedText(display, Qt.ElideRight, max_width)
        tw = fm.horizontalAdvance(display)
        th = fm.height()
        p.drawText(QPointF(tx - tw / 2, ty + th / 4), display)

    def _draw_centre(self, p: QPainter, c: QPointF, r: float) -> None:
        """Draw the centre circle showing input file info."""
        if self._global_mode and not self._file_paths:
            # Background circle
            p.setPen(Qt.NoPen)
            bg_color = QColor("#382323") if self._hovered_center else QColor("#252525")
            p.setBrush(QBrush(bg_color))
            p.drawEllipse(c, r, r)

            # Border ring
            border_pen = QPen(QColor("#FF453A") if self._hovered_center else ACCENT, 2.0)
            p.setPen(border_pen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(c, r, r)

            if self._hovered_center:
                p.setPen(QPen(QColor("#FF453A")))
                p.setFont(QFont("Sans", 12, QFont.Bold))
                fm = QFontMetrics(p.font())
                cancel_text = "✕ CANCEL"
                p.drawText(
                    QPointF(c.x() - fm.horizontalAdvance(cancel_text) / 2, c.y() - 2),
                    cancel_text,
                )
                p.setPen(QPen(TEXT_GREY))
                p.setFont(QFont("Sans", 8))
                fm2 = QFontMetrics(p.font())
                sub_text = "Release to dismiss"
                p.drawText(
                    QPointF(c.x() - fm2.horizontalAdvance(sub_text) / 2, c.y() + 16),
                    sub_text,
                )
                return

            # Title
            title = self._wheel.upper()
            p.setPen(QPen(ACCENT))
            p.setFont(QFont("Sans", 11, QFont.Bold))
            fm = QFontMetrics(p.font())
            p.drawText(
                QPointF(c.x() - fm.horizontalAdvance(title) / 2, c.y() - 2),
                title,
            )

            # Subtitle
            p.setPen(QPen(TEXT_GREY))
            p.setFont(QFont("Sans", 8))
            fm2 = QFontMetrics(p.font())
            sub_text = "Drag file here"
            p.drawText(
                QPointF(c.x() - fm2.horizontalAdvance(sub_text) / 2, c.y() + 16),
                sub_text,
            )
            return

        # File info text
        if self._file_paths:
            name = os.path.basename(self._file_paths[0])
            ext = os.path.splitext(name)[1].lstrip(".").upper() or "FILE"
            if len(self._file_paths) > 1:
                name = f"{len(self._file_paths)} files"

            # Extension label
            p.setPen(QPen(ACCENT))
            p.setFont(QFont("Sans", 13, QFont.Bold))
            fm = QFontMetrics(p.font())
            p.drawText(
                QPointF(c.x() - fm.horizontalAdvance(ext) / 2, c.y() - 2),
                ext,
            )

            # Filename (truncated)
            p.setPen(QPen(TEXT_GREY))
            p.setFont(QFont("Sans", 8))
            fm2 = QFontMetrics(p.font())
            display_name = fm2.elidedText(name, Qt.ElideMiddle, int(r * 1.6))
            p.drawText(
                QPointF(c.x() - fm2.horizontalAdvance(display_name) / 2, c.y() + 16),
                display_name,
            )
        else:
            p.setPen(QPen(TEXT_GREY))
            p.setFont(QFont("Sans", 10))
            p.drawText(QPointF(c.x() - 15, c.y() + 5), "...")

    def _draw_toggle(self, p: QPainter) -> None:
        """Draw the small Formats/Tools toggle button."""
        rect = self._toggle_rect()
        path = QPainterPath()
        path.addRoundedRect(rect, 13, 13)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#3a3a3a")))
        p.drawPath(path)

        p.setPen(QPen(ACCENT, 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

        label = {"formats": "⇧ Formats", "tools": "⌘ Tools", "actions": "⌃ Actions"}[self._wheel]
        p.setPen(QPen(TEXT_WHITE))
        p.setFont(QFont("Sans", 9, QFont.DemiBold))
        p.drawText(rect, Qt.AlignCenter, label)