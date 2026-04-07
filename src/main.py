"""Application entry point coordinating capture and annotation overlay."""

from __future__ import annotations

import sys
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gio, GLib, Gtk  # noqa: E402

from .capture import ScreenCapture
from .overlay import OverlayWindow
from .tray import register_tray_icon

APP_ID = "io.github.fallenshot"


class FallenshotApp(Gtk.Application):
    """GTK application that captures screenshots and opens the annotation overlay."""

    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self._capture_service = ScreenCapture()
        self._overlay_window: OverlayWindow | None = None
        self._capture_in_progress = False
        self._tray_mode_enabled = False

    def do_startup(self) -> None:
        """Initialize application actions and shortcuts."""
        Gtk.Application.do_startup(self)

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["Escape"])

    def do_activate(self) -> None:
        """Activate the app, preferring tray icon mode when available."""
        self.hold()

        self._tray_mode_enabled = register_tray_icon(
            on_capture=self._on_tray_capture,
            on_capture5=self._on_tray_capture5,
            on_quit=self.quit,
        )

        if not self._tray_mode_enabled:
            print("[main] Tray indicator unavailable; starting direct capture mode.")
            GLib.timeout_add(150, self._start_capture)

    def _on_tray_capture(self, *_: Any) -> None:
        """Trigger an immediate capture from the tray icon."""
        if self._capture_in_progress:
            return
        self._capture_in_progress = True
        GLib.timeout_add(150, self._start_capture)

    def _on_tray_capture5(self, *_: Any) -> None:
        """Trigger a capture after a 5-second delay."""
        if self._capture_in_progress:
            return
        self._capture_in_progress = True
        GLib.timeout_add(5000, self._start_capture)

    def _start_capture(self) -> bool:
        """Request a screenshot and keep timeout callback single-shot."""
        self._capture_service.capture(callback=self._on_screenshot_ready)
        return False

    def _on_screenshot_ready(self, screenshot_pixbuf: Any) -> None:
        """Open annotation UI when a screenshot is available."""
        self._capture_in_progress = False

        if screenshot_pixbuf is None:
            print("[main] Screenshot capture was cancelled or failed.")
            if not self._tray_mode_enabled:
                self.release()
                self.quit()
            return

        if not self._tray_mode_enabled:
            self.release()

        self._overlay_window = OverlayWindow(self, screenshot_pixbuf)
        image_width = screenshot_pixbuf.get_width()
        image_height = screenshot_pixbuf.get_height()
        self._overlay_window.start_annotation(0, 0, image_width, image_height)
        self._overlay_window.present()


def run() -> None:
    """Run the Fallenshot GTK application."""
    app = FallenshotApp()
    sys.exit(app.run(sys.argv))
