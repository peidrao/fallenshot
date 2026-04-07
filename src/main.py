"""Application entry point coordinating capture and annotation overlay."""

from __future__ import annotations

import sys
from typing import Any

import gi


gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

_HAS_INDICATOR = False
try:
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as AppIndicator3

    _HAS_INDICATOR = True
except (ValueError, ImportError):
    try:
        gi.require_version("AppIndicator3", "0.1")
        from gi.repository import AppIndicator3

        _HAS_INDICATOR = True
    except (ValueError, ImportError):
        AppIndicator3 = None

from gi.repository import Gio, GLib, Gtk

from .capture import ScreenCapture
from .overlay import OverlayWindow

APP_ID = "io.github.fallenshot"
_HAS_LEGACY_GTK_MENU = all(
    hasattr(Gtk, attribute_name)
    for attribute_name in ("Menu", "MenuItem", "SeparatorMenuItem")
)


class FallenshotApp(Gtk.Application):
    """GTK application that captures screenshots and opens the annotation overlay."""

    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self._capture_service = ScreenCapture()
        self._overlay_window: OverlayWindow | None = None
        self._indicator = None
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
        self._tray_mode_enabled = _HAS_INDICATOR and _HAS_LEGACY_GTK_MENU

        if self._tray_mode_enabled:
            self._setup_indicator()
            return

        print("[main] Tray indicator unavailable; starting direct capture mode.")
        GLib.timeout_add(150, self._start_capture)

    def _setup_indicator(self) -> None:
        """Create the system tray indicator and action menu."""
        self._indicator = AppIndicator3.Indicator.new(
            APP_ID,
            "io.github.fallenshot",
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self._indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self._indicator.set_icon_full("io.github.fallenshot", "Fallenshot")

        menu = Gtk.Menu()

        capture_item = Gtk.MenuItem(label="Capture screenshot")
        capture_item.connect("activate", self._on_tray_capture)
        menu.append(capture_item)

        menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", lambda _: self.quit())
        menu.append(quit_item)

        menu.show_all()
        self._indicator.set_menu(menu)

        self._indicator.connect("scroll-event", None)
        try:
            self._indicator.set_secondary_activate_target(capture_item)
        except Exception:
            pass

        print("[main] Tray indicator is active; click it to start a capture.")

    def _on_tray_capture(self, *_: Any) -> None:
        """Trigger a capture request from the tray menu."""
        if self._capture_in_progress:
            return

        self._capture_in_progress = True
        GLib.timeout_add(150, self._start_capture)

    def _start_capture(self) -> bool:
        """Request a screenshot and keep timeout callback single-shot."""
        self._capture_service.capture(callback=self._on_screenshot_ready)
        return False

    def _on_screenshot_ready(self, screenshot_pixbuf) -> None:
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
