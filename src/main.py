"""
main.py — Ponto de entrada: Gtk.Application que orquestra capture → overlay.
"""

import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

# Tenta carregar o indicador de bandeja do sistema
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

from gi.repository import Gtk, GLib, Gio

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
        self._indicator = None
        self._capturing = False

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def do_startup(self):
        Gtk.Application.do_startup(self)

        action = Gio.SimpleAction.new("quit", None)
        action.connect("activate", lambda *_: self.quit())
        self.add_action(action)
        self.set_accels_for_action("app.quit", ["Escape"])

    def do_activate(self):
        """Cria o ícone na barra do GNOME e aguarda clique do usuário."""
        # hold() impede o GLib main loop de encerrar enquanto não há janelas
        self.hold()

        if _HAS_INDICATOR:
            self._setup_indicator()
        else:
            # Fallback: captura imediatamente (comportamento antigo)
            print("[main] Indicador de bandeja não disponível. Iniciando captura direta.")
            GLib.timeout_add(150, self._start_capture)

    def _setup_indicator(self):
        """Cria o AppIndicator na barra do GNOME."""
        self._indicator = AppIndicator3.Indicator.new(
            APP_ID,
            "io.github.fallenshot",
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self._indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)

        # Tenta usar o ícone do app; se não encontrar, usa ícone genérico
        self._indicator.set_icon_full("io.github.fallenshot", "Fallenshot")

        # Menu com opção de capturar e sair
        menu = Gtk.Menu()

        item_capture = Gtk.MenuItem(label="Capturar screenshot")
        item_capture.connect("activate", self._on_tray_capture)
        menu.append(item_capture)

        menu.append(Gtk.SeparatorMenuItem())

        item_quit = Gtk.MenuItem(label="Sair")
        item_quit.connect("activate", lambda _: self.quit())
        menu.append(item_quit)

        menu.show_all()
        self._indicator.set_menu(menu)

        # Clique primário no ícone também dispara captura
        self._indicator.connect("scroll-event", None)
        try:
            self._indicator.set_secondary_activate_target(item_capture)
        except Exception:
            pass

        print("[main] Ícone criado na barra do GNOME. Clique para capturar.")

    def _on_tray_capture(self, *_):
        """Chamado ao clicar em 'Capturar screenshot' no menu da bandeja."""
        if self._capturing:
            return
        self._capturing = True
        GLib.timeout_add(150, self._start_capture)

    def _start_capture(self):
        self._capture.capture(callback=self._on_screenshot_ready)
        return False  # não repetir

    def _on_screenshot_ready(self, pixbuf):
        self._capturing = False

        if pixbuf is None:
            print("[main] Captura cancelada ou falhou.")
            if not _HAS_INDICATOR:
                self.release()
                self.quit()
            return

        if not _HAS_INDICATOR:
            # Modo legado: libera o hold após capturar
            self.release()

        self._window = OverlayWindow(self, pixbuf)
        w = pixbuf.get_width()
        h = pixbuf.get_height()
        self._window.start_annotation(0, 0, w, h)
        self._window.present()


def run():
    app = FallenshotApp()
    sys.exit(app.run(sys.argv))
