"""Application entry point coordinating capture, selection, and annotation."""

from __future__ import annotations

import sys
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import GdkPixbuf, Gio, GLib, Gtk

from .overlay import OverlayWindow
from .screencast import ScreenCastSession
from .selector import SelectorWindow
from .tray import register_tray_icon

APP_ID = "io.github.fallenshot"


class FallenshotApp(Gtk.Application):
    """GTK application — tray icon → frame capture → region select → annotate."""

    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self._cast = ScreenCastSession()
        self._capture_in_progress = False
        self._tray_mode_enabled = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["Escape"])

    def do_activate(self) -> None:
        self.hold()
        self._tray_mode_enabled = register_tray_icon(
            on_capture=self._trigger_capture,
            on_capture5=self._trigger_capture_delayed,
            on_quit=self.quit,
        )
        if not self._tray_mode_enabled:
            print("[main] Tray unavailable — capturing immediately.")
            GLib.timeout_add(150, self._start_capture)

    # ------------------------------------------------------------------
    # Tray callbacks
    # ------------------------------------------------------------------

    def _trigger_capture(self, *_: Any) -> None:
        if self._capture_in_progress:
            return
        self._capture_in_progress = True
        GLib.timeout_add(150, self._start_capture)

    def _trigger_capture_delayed(self, *_: Any) -> None:
        if self._capture_in_progress:
            return
        self._capture_in_progress = True
        GLib.timeout_add(5000, self._start_capture)

    # ------------------------------------------------------------------
    # Capture → select → annotate pipeline
    # ------------------------------------------------------------------

    def _start_capture(self) -> bool:
        self._cast.capture_frame(callback=self._on_frame_ready)
        return False

    def _on_frame_ready(self, pixbuf: GdkPixbuf.Pixbuf | None) -> None:
        """Frame received from PipeWire — open the region selector."""
        if pixbuf is None:
            print("[main] Capture failed or was cancelled.")
            self._capture_in_progress = False
            return

        selector = SelectorWindow(
            self,
            pixbuf,
            on_selected=self._on_region_selected,
            on_cancelled=self._on_selection_cancelled,
        )
        selector.present()

    def _on_region_selected(
        self,
        pixbuf: GdkPixbuf.Pixbuf,
        x: int, y: int, w: int, h: int,
    ) -> None:
        """User confirmed a region — open the annotation overlay."""
        self._capture_in_progress = False
        overlay = OverlayWindow(self, pixbuf)
        overlay.start_annotation(x, y, w, h)
        overlay.present()

    def _on_selection_cancelled(self) -> None:
        self._capture_in_progress = False


def run() -> None:
    """Run the Fallenshot GTK application."""
    app = FallenshotApp()
    sys.exit(app.run(sys.argv))
