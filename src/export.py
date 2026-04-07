"""Clipboard and file export utilities for annotated screenshots."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from datetime import datetime

import cairo
import gi


gi.require_version("Gtk", "4.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import GdkPixbuf, Gio, Gtk

Selection = tuple[int, int, int, int]
SaveCallback = Callable[[str | None], None]


class ExportManager:
    """Handle clipboard copy and PNG saving for rendered screenshot surfaces."""

    def __init__(self, parent_window: Gtk.Window) -> None:
        self._parent_window = parent_window

    def copy_surface_to_clipboard(
        self,
        surface: cairo.ImageSurface,
        selection: Selection,
    ) -> bool:
        """
        Copy a selection from a rendered surface to the Wayland clipboard.

        Args:
            surface: Rendered screenshot image surface.
            selection: ``(x, y, width, height)`` crop rectangle on the surface.

        Returns:
            bool: ``True`` when the clipboard operation was started successfully.
        """
        if shutil.which("wl-copy") is None:
            print("[export] wl-copy is not available; install wl-clipboard.")
            return False

        cropped_image = self._crop_surface(surface, selection)
        if cropped_image is None:
            return False

        temporary_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        try:
            cropped_image.savev(temporary_file.name, "png", [], [])
            temporary_file.close()
            with open(temporary_file.name, "rb") as image_stream:
                subprocess.run(
                    ["wl-copy", "--type", "image/png"],
                    stdin=image_stream,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
        finally:
            os.unlink(temporary_file.name)

        return True

    def save_surface_to_file(
        self,
        surface: cairo.ImageSurface,
        selection: Selection,
        on_done: SaveCallback | None = None,
    ) -> None:
        """
        Open a save dialog and persist the selected screenshot region as PNG.

        Args:
            surface: Rendered screenshot image surface.
            selection: ``(x, y, width, height)`` crop rectangle on the surface.
            on_done: Optional callback receiving saved file path or ``None``.
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        default_filename = f"fallenshot-{timestamp}.png"

        default_directory = os.path.expanduser("~/Pictures/Screenshots")
        os.makedirs(default_directory, exist_ok=True)

        save_dialog = Gtk.FileChooserDialog(
            title="Save screenshot",
            transient_for=self._parent_window,
            action=Gtk.FileChooserAction.SAVE,
        )
        save_dialog.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        save_dialog.add_button("_Save", Gtk.ResponseType.ACCEPT)
        save_dialog.set_current_name(default_filename)
        save_dialog.set_current_folder(Gio.File.new_for_path(default_directory))

        png_filter = Gtk.FileFilter()
        png_filter.set_name("PNG images")
        png_filter.add_mime_type("image/png")
        save_dialog.add_filter(png_filter)

        def on_dialog_response(dialog: Gtk.FileChooserDialog, response: Gtk.ResponseType) -> None:
            dialog.destroy()
            if response != Gtk.ResponseType.ACCEPT:
                if on_done is not None:
                    on_done(None)
                return

            selected_file = dialog.get_file()
            if selected_file is None:
                if on_done is not None:
                    on_done(None)
                return

            output_path = selected_file.get_path() or ""
            if not output_path:
                if on_done is not None:
                    on_done(None)
                return

            if not output_path.endswith(".png"):
                output_path += ".png"

            try:
                cropped_image = self._crop_surface(surface, selection)
                if cropped_image is None:
                    raise ValueError("Invalid crop selection.")
                cropped_image.savev(output_path, "png", [], [])
                if on_done is not None:
                    on_done(output_path)
            except Exception as error:
                print(f"[export] Failed to save screenshot: {error}")
                if on_done is not None:
                    on_done(None)

        save_dialog.connect("response", on_dialog_response)
        save_dialog.present()

    @staticmethod
    def _crop_surface(
        surface: cairo.ImageSurface,
        selection: Selection,
    ) -> GdkPixbuf.Pixbuf | None:
        """Convert a Cairo surface to a pixbuf and return a bounded crop."""
        x, y, width, height = selection
        source_image = ExportManager._surface_to_pixbuf(surface)
        if source_image is None:
            return None

        bounded_width = min(width, source_image.get_width() - x)
        bounded_height = min(height, source_image.get_height() - y)
        if bounded_width <= 0 or bounded_height <= 0:
            return None

        return source_image.new_subpixbuf(x, y, bounded_width, bounded_height)

    @staticmethod
    def _surface_to_pixbuf(surface: cairo.ImageSurface) -> GdkPixbuf.Pixbuf | None:
        """Encode a Cairo surface as PNG and load it into a pixbuf."""
        png_buffer = io.BytesIO()
        try:
            surface.write_to_png(png_buffer)
            png_buffer.seek(0)

            loader = GdkPixbuf.PixbufLoader.new_with_type("png")
            loader.write(png_buffer.read())
            loader.close()
            return loader.get_pixbuf()
        except Exception as error:
            print(f"[export] Failed to convert surface to pixbuf: {error}")
            return None
