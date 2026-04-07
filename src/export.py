"""
export.py — Exportação: clipboard Wayland nativo e salvar PNG.
"""

import io
import os
import shutil
import subprocess
import tempfile
from datetime import datetime

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gdk, GdkPixbuf, Gtk, Gio


class ExportManager:
    def __init__(self, parent_window: Gtk.Window):
        self._parent = parent_window

    # ------------------------------------------------------------------
    # Clipboard
    # ------------------------------------------------------------------

    def copy_surface_to_clipboard(self, surface, selection):
        """
        Copia a região `selection` para o clipboard via wl-copy.
        Usa wl-copy (wl-clipboard) que persiste mesmo após o app fechar.
        """
        if not shutil.which("wl-copy"):
            print("[export] wl-copy não encontrado. Instale: sudo apt install wl-clipboard")
            return False

        x, y, w, h = (int(v) for v in selection)

        buf = io.BytesIO()
        surface.write_to_png(buf)
        buf.seek(0)

        loader = GdkPixbuf.PixbufLoader.new_with_type("png")
        loader.write(buf.read())
        loader.close()
        full_pixbuf = loader.get_pixbuf()

        w = min(w, full_pixbuf.get_width() - x)
        h = min(h, full_pixbuf.get_height() - y)
        if w <= 0 or h <= 0:
            return False

        cropped = full_pixbuf.new_subpixbuf(x, y, w, h)

        # Salva em arquivo temporário e envia para wl-copy
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        try:
            cropped.savev(tmp.name, "png", [], [])
            tmp.close()
            with open(tmp.name, "rb") as f:
                subprocess.Popen(
                    ["wl-copy", "--type", "image/png"],
                    stdin=f,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        finally:
            os.unlink(tmp.name)

        return True

    # ------------------------------------------------------------------
    # Salvar arquivo — nome automático com timestamp, fecha o app após salvar
    # ------------------------------------------------------------------

    def save_surface_to_file(self, surface, selection, on_done=None):
        """
        Abre FileChooserDialog com nome sugerido fallenshot-TIMESTAMP.png.
        Pasta padrão: ~/Pictures/Screenshots.
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        default_name = f"fallenshot-{timestamp}.png"

        save_dir = os.path.expanduser("~/Pictures/Screenshots")
        os.makedirs(save_dir, exist_ok=True)

        dialog = Gtk.FileChooserDialog(
            title="Salvar screenshot",
            transient_for=self._parent,
            action=Gtk.FileChooserAction.SAVE,
        )
        dialog.add_button("_Cancelar", Gtk.ResponseType.CANCEL)
        dialog.add_button("_Salvar", Gtk.ResponseType.ACCEPT)
        dialog.set_current_name(default_name)
        dialog.set_current_folder(Gio.File.new_for_path(save_dir))

        png_filter = Gtk.FileFilter()
        png_filter.set_name("PNG images")
        png_filter.add_mime_type("image/png")
        dialog.add_filter(png_filter)

        def _on_response(dlg, response):
            dlg.destroy()
            if response != Gtk.ResponseType.ACCEPT:
                if on_done:
                    on_done(None)
                return

            path = dlg.get_file().get_path()
            if not path.endswith(".png"):
                path += ".png"

            try:
                x, y, w, h = (int(v) for v in selection)
                buf = io.BytesIO()
                surface.write_to_png(buf)
                buf.seek(0)

                loader = GdkPixbuf.PixbufLoader.new_with_type("png")
                loader.write(buf.read())
                loader.close()
                full = loader.get_pixbuf()

                w = min(w, full.get_width() - x)
                h = min(h, full.get_height() - y)
                cropped = full.new_subpixbuf(x, y, w, h)
                cropped.savev(path, "png", [], [])

                if on_done:
                    on_done(path)
            except Exception as e:
                print(f"[export] Erro ao salvar: {e}")
                if on_done:
                    on_done(None)

        dialog.connect("response", _on_response)
        dialog.present()
