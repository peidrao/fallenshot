from __future__ import annotations

from src import tray


def test_load_icon_pixmap_converts_rgba_to_argb(monkeypatch):
    class FakePB:
        def convert(self, *_args, **_kwargs):
            return self

        def get_pixels(self):
            # RGBA: (10,20,30,40) and (1,2,3,4)
            return bytes([10, 20, 30, 40, 1, 2, 3, 4])

    monkeypatch.setattr(tray.GdkPixbuf.Pixbuf, "new_from_file_at_size", staticmethod(lambda *a: FakePB()))

    pixmaps = tray._load_icon_pixmap("icon.png")
    raw = bytes(pixmaps[0][2])
    assert raw == bytes([40, 10, 20, 30, 4, 1, 2, 3])


def test_dbusmenu_event_dispatches_callbacks(monkeypatch):
    calls = []
    monkeypatch.setattr(tray.GLib, "idle_add", lambda fn: calls.append(fn.__name__))

    menu = tray._DbusMenu(
        tray.dbus.SessionBus(),
        on_capture=lambda: None,
        on_capture5=lambda: None,
        on_quit=lambda: None,
    )

    menu.Event(1, "clicked", None, 0)
    menu.Event(2, "clicked", None, 0)
    menu.Event(4, "clicked", None, 0)
    menu.Event(999, "ignored", None, 0)

    assert len(calls) == 3


def test_register_tray_icon_success(monkeypatch):
    class FakeWatcher:
        def __init__(self):
            self.calls = []

        def RegisterStatusNotifierItem(self, name):
            self.calls.append(name)

    watcher = FakeWatcher()

    class FakeBus:
        def get_object(self, _name, _path):
            return watcher

    monkeypatch.setattr(tray.dbus, "SessionBus", lambda: FakeBus())
    monkeypatch.setattr(tray.dbus, "Interface", lambda obj, _iface: obj)
    monkeypatch.setattr(tray, "_load_icon_pixmap", lambda _path: [])

    ok = tray.register_tray_icon(lambda: None, lambda: None, lambda: None)

    assert ok is True
    assert len(watcher.calls) == 1


def test_register_tray_icon_failure(monkeypatch):
    monkeypatch.setattr(tray.dbus, "SessionBus", lambda: (_ for _ in ()).throw(RuntimeError("no bus")))

    ok = tray.register_tray_icon(lambda: None, lambda: None, lambda: None)

    assert ok is False
