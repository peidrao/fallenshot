"""
capture.py — Captura de tela via xdg-desktop-portal (Wayland nativo).

Fluxo:
  1. Chama org.freedesktop.portal.Screenshot via DBus
  2. O portal exibe sua própria UI de seleção de monitor (se disponível)
  3. Retorna URI de arquivo temporário com o screenshot
  4. Carrega como GdkPixbuf e chama o callback
"""

import gi
gi.require_version("GdkPixbuf", "2.0")

import dbus
import dbus.mainloop.glib

from gi.repository import GLib, GdkPixbuf, Gio


class ScreenCapture:
    def __init__(self):
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        self._bus = dbus.SessionBus()
        self._callback = None
        self._signal_match = None

    def capture(self, callback, interactive=True):
        """
        Inicia captura de tela via xdg-desktop-portal.

        Args:
            callback: chamado com (GdkPixbuf | None) quando pronto
            interactive: se True, permite o portal mostrar UI de seleção
        """
        self._callback = callback

        try:
            portal_obj = self._bus.get_object(
                "org.freedesktop.portal.Desktop",
                "/org/freedesktop/portal/desktop",
            )
            screenshot_iface = dbus.Interface(
                portal_obj, "org.freedesktop.portal.Screenshot"
            )

            handle_token = f"newflameshot{GLib.get_monotonic_time()}"
            options = {
                "handle_token": dbus.String(handle_token, variant_level=1),
                "interactive": dbus.Boolean(interactive, variant_level=1),
            }

            request_path = screenshot_iface.Screenshot("", options)

            request_obj = self._bus.get_object(
                "org.freedesktop.portal.Desktop", request_path
            )
            self._signal_match = request_obj.connect_to_signal(
                "Response", self._on_response
            )

        except dbus.DBusException as e:
            print(f"[capture] Erro DBus: {e}")
            if self._callback:
                GLib.idle_add(self._callback, None)

    def _on_response(self, response_code, results):
        if self._signal_match:
            self._signal_match.remove()
            self._signal_match = None

        if response_code != 0:
            print(f"[capture] Portal cancelado ou erro (code={response_code})")
            GLib.idle_add(self._callback, None)
            return

        uri = str(results.get("uri", ""))
        if not uri:
            print("[capture] URI vazia na resposta do portal")
            GLib.idle_add(self._callback, None)
            return

        try:
            gfile = Gio.File.new_for_uri(uri)
            path = gfile.get_path()
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
            # Nota: arquivo salvo pelo portal em ~/Pictures/Screenshots — não apagar
            GLib.idle_add(self._callback, pixbuf)

        except Exception as e:
            print(f"[capture] Erro ao carregar imagem: {e}")
            GLib.idle_add(self._callback, None)
