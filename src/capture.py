"""Wayland screenshot capture through xdg-desktop-portal."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable

import dbus
import dbus.mainloop.glib
import gi


gi.require_version("GdkPixbuf", "2.0")

from gi.repository import GdkPixbuf, Gio, GLib

CaptureCallback = Callable[[GdkPixbuf.Pixbuf | None], None]


class ScreenCapture:
    """Request screenshots from the desktop portal and return loaded pixbufs."""

    def __init__(self) -> None:
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        self._session_bus = dbus.SessionBus()
        self._callback: CaptureCallback | None = None
        self._response_signal = None

    def capture(self, callback: CaptureCallback, interactive: bool = True) -> None:
        """
        Start a screenshot request through ``org.freedesktop.portal.Screenshot``.

        Args:
            callback: Function called with a loaded screenshot pixbuf, or ``None`` on failure.
            interactive: When ``True``, allow the portal to show monitor-selection UI.
        """
        self._callback = callback

        try:
            portal = self._session_bus.get_object(
                "org.freedesktop.portal.Desktop",
                "/org/freedesktop/portal/desktop",
            )
            screenshot_api = dbus.Interface(portal, "org.freedesktop.portal.Screenshot")

            request_token = f"fallenshot{GLib.get_monotonic_time()}"
            options = {
                "handle_token": dbus.String(request_token, variant_level=1),
                "interactive": dbus.Boolean(interactive, variant_level=1),
            }
            request_path = screenshot_api.Screenshot("", options)

            request = self._session_bus.get_object(
                "org.freedesktop.portal.Desktop",
                request_path,
            )
            self._response_signal = request.connect_to_signal("Response", self._on_response)
        except dbus.DBusException as error:
            print(f"[capture] DBus request failed: {error}")
            self._dispatch(None)

    def _on_response(self, response_code: int, results: Mapping[str, Any]) -> None:
        """Handle the portal response and load the returned screenshot URI."""
        if self._response_signal is not None:
            self._response_signal.remove()
            self._response_signal = None

        if response_code != 0:
            print(f"[capture] Portal request cancelled or failed (code={response_code}).")
            self._dispatch(None)
            return

        screenshot_uri = str(results.get("uri", ""))
        if not screenshot_uri:
            print("[capture] Portal response did not include a screenshot URI.")
            self._dispatch(None)
            return

        try:
            file_path = Gio.File.new_for_uri(screenshot_uri).get_path()
            if not file_path:
                raise RuntimeError("Portal URI could not be mapped to a local file path.")

            screenshot_pixbuf = GdkPixbuf.Pixbuf.new_from_file(file_path)
            self._dispatch(screenshot_pixbuf)
        except Exception as error:
            print(f"[capture] Failed to load screenshot file: {error}")
            self._dispatch(None)

    def _dispatch(self, pixbuf: GdkPixbuf.Pixbuf | None) -> None:
        """Invoke the capture callback on the GLib main loop."""
        if self._callback is None:
            return
        GLib.idle_add(self._callback, pixbuf)
