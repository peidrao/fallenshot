"""
main.py — Ponto de entrada: Gtk.Application que orquestra capture → overlay.
"""

import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gtk, Gdk, GLib, Gio

from .capture import ScreenCapture
from .overlay import OverlayWindow


APP_ID = "io.github.fallenshot"


class FallenshotApp(Gtk.Application):
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self._capture = ScreenCapture()
        self._window = None

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def do_activate(self):
        """Inicia captura imediatamente ao ativar o app."""
        # hold() impede o GLib main loop de encerrar enquanto não há janelas
        self.hold()
        GLib.timeout_add(150, self._start_capture)

    def _start_capture(self):
        self._capture.capture(callback=self._on_screenshot_ready)
        return False  # não repetir

    def _on_screenshot_ready(self, pixbuf):
        # release() emparelha com o hold() feito em do_activate
        self.release()

        if pixbuf is None:
            print("[main] Captura cancelada ou falhou.")
            self.quit()
            return

        self._window = OverlayWindow(self, pixbuf)
        # Portal já fez a seleção — vai direto para annotation com a imagem completa
        w = pixbuf.get_width()
        h = pixbuf.get_height()
        self._window.start_annotation(0, 0, w, h)
        self._window.present()

    # ------------------------------------------------------------------
    # Ação global PrintScreen (opcional, requer permissão do compositor)
    # ------------------------------------------------------------------

    def do_startup(self):
        Gtk.Application.do_startup(self)

        action = Gio.SimpleAction.new("quit", None)
        action.connect("activate", lambda *_: self.quit())
        self.add_action(action)
        self.set_accels_for_action("app.quit", ["Escape"])


def run():
    app = FallenshotApp()
    sys.exit(app.run(sys.argv))
