"""Best-effort global X11 drag monitor for the background converter.

Wayland intentionally prevents ordinary applications from observing global
pointer/drag state. X11 exposes enough state to activate the ring after a
mouse drag begins and a modifier is held; the actual file paths still arrive
through the normal Xdnd MIME payload.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import time

from PySide6.QtCore import QObject, QPoint, QTimer, Qt
from PySide6.QtGui import QCursor


class _X11Pointer:
    """Tiny ctypes wrapper so Xlib is optional and no Python package is needed."""

    BUTTON1_MASK = 1 << 8
    SHIFT_MASK = 1 << 0
    CONTROL_MASK = 1 << 2
    META_MASK = 1 << 6

    def __init__(self) -> None:
        self._lib = None
        self._display = None
        library = ctypes.util.find_library("X11")
        if not library:
            return
        try:
            self._lib = ctypes.CDLL(library)
            self._lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
            self._lib.XOpenDisplay.restype = ctypes.c_void_p
            self._lib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
            self._lib.XDefaultRootWindow.restype = ctypes.c_ulong
            self._lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
            self._lib.XQueryPointer.argtypes = [
                ctypes.c_void_p,
                ctypes.c_ulong,
                ctypes.POINTER(ctypes.c_ulong),
                ctypes.POINTER(ctypes.c_ulong),
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_uint),
            ]
            self._lib.XQueryPointer.restype = ctypes.c_int
            self._display = self._lib.XOpenDisplay(None)
            self._root = self._lib.XDefaultRootWindow(self._display) if self._display else 0
        except OSError:
            self._lib = None

    @property
    def available(self) -> bool:
        return bool(self._lib and self._display)

    def state(self) -> tuple[bool, int, int, int] | None:
        if not self.available:
            return None
        root = ctypes.c_ulong()
        child = ctypes.c_ulong()
        root_x = ctypes.c_int()
        root_y = ctypes.c_int()
        win_x = ctypes.c_int()
        win_y = ctypes.c_int()
        mask = ctypes.c_uint()
        ok = self._lib.XQueryPointer(
            self._display,
            self._root,
            ctypes.byref(root),
            ctypes.byref(child),
            ctypes.byref(root_x),
            ctypes.byref(root_y),
            ctypes.byref(win_x),
            ctypes.byref(win_y),
            ctypes.byref(mask),
        )
        if not ok:
            return None
        return bool(mask.value & self.BUTTON1_MASK), root_x.value, root_y.value, mask.value

    def close(self) -> None:
        if self.available:
            self._lib.XCloseDisplay(self._display)
            self._display = None

    def __del__(self) -> None:
        self.close()


class GlobalDragMonitor(QObject):
    """Activate a ring on Shift/Ctrl/Super while dragging on X11."""

    def __init__(self, radial_menu, parent=None) -> None:
        super().__init__(parent)
        self._menu = radial_menu
        self._x11 = _X11Pointer()
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._poll)
        self._timer.start()
        self._button_started_at: float | None = None
        self._press_origin: tuple[int, int] | None = None
        self._active = False
        self._mode: str | None = None

    def _poll(self) -> None:
        state = self._x11.state()
        if state is None:
            return
        button_down, x, y, mask = state
        now = time.monotonic()
        if button_down and self._button_started_at is None:
            self._button_started_at = now
            self._press_origin = (x, y)
        if not button_down:
            self._button_started_at = None
            self._press_origin = None
            if self._active:
                self._active = False
                self._mode = None
                QTimer.singleShot(60, self._menu.dismiss)
            return

        mode = self._mode_for_mask(mask)
        if not self._active and mode and self._button_started_at is not None:
            # Require actual movement before taking the pointer. This lets
            # the file manager create its Xdnd session first; showing the
            # target on a stationary button press would steal the drag.
            moved = False
            if self._press_origin is not None:
                dx = x - self._press_origin[0]
                dy = y - self._press_origin[1]
                moved = (dx * dx + dy * dy) >= 64
            if now - self._button_started_at >= 0.08 and moved:
                self._active = True
                self._mode = mode
                self._menu.show_global(mode, QPoint(x, y))
        elif self._active:
            if mode and mode != self._mode:
                self._mode = mode
                self._menu.set_wheel(mode)
            self._menu.update_global_cursor(QPoint(x, y))

    @classmethod
    def _mode_for_mask(cls, mask: int) -> str | None:
        if mask & _X11Pointer.SHIFT_MASK:
            return "formats"
        if mask & (_X11Pointer.CONTROL_MASK | _X11Pointer.META_MASK):
            return "tools"
        return None

    def stop(self) -> None:
        self._timer.stop()
        self._x11.close()
