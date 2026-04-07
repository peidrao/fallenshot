from __future__ import annotations

from src import tray


def test_load_icon_pixmap_converts_rgba_to_argb(monkeypatch):
    class FakePB:
        def get_width(self):
            return 2

        def get_height(self):
            return 1

        def get_n_channels(self):
            return 4

        def get_has_alpha(self):
            return True

        def get_rowstride(self):
            return 8

        def get_pixels(self):
            # RGBA: (10,20,30,40) and (1,2,3,4)
            return bytes([10, 20, 30, 40, 1, 2, 3, 4])

    monkeypatch.setattr(
        tray.GdkPixbuf.Pixbuf,
        "new_from_file_at_size",
        staticmethod(lambda *a: FakePB()),
    )

    pixmaps = tray._load_icon_pixmap("icon.png")
    raw = bytes(pixmaps[0][2])
    assert raw == bytes([40, 10, 20, 30, 4, 1, 2, 3])


def test_load_icon_pixmap_rgb_assumes_opaque_alpha(monkeypatch):
    class FakePB:
        def get_width(self):
            return 1

        def get_height(self):
            return 1

        def get_n_channels(self):
            return 3

        def get_has_alpha(self):
            return False

        def get_rowstride(self):
            return 3

        def get_pixels(self):
            return bytes([7, 8, 9])

    monkeypatch.setattr(
        tray.GdkPixbuf.Pixbuf,
        "new_from_file_at_size",
        staticmethod(lambda *a: FakePB()),
    )
    pixmaps = tray._load_icon_pixmap("icon.png")
    assert bytes(pixmaps[0][2]) == bytes([255, 7, 8, 9])


def test_load_icon_pixmap_failure_returns_empty(monkeypatch):
    monkeypatch.setattr(
        tray.GdkPixbuf.Pixbuf,
        "new_from_file_at_size",
        staticmethod(lambda *a: (_ for _ in ()).throw(RuntimeError("bad icon"))),
    )
    assert tray._load_icon_pixmap("icon.png") == []


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


def test_dbusmenu_eventgroup_dispatches_each_event(monkeypatch):
    called = []
    menu = tray._DbusMenu(
        tray.dbus.SessionBus(),
        on_capture=lambda: None,
        on_capture5=lambda: None,
        on_quit=lambda: None,
    )
    monkeypatch.setattr(
        menu,
        "Event",
        lambda item_id, event_id, data, timestamp: called.append((item_id, event_id)),
    )
    menu.EventGroup([(1, "clicked", None, 0), (2, "clicked", None, 0)])
    assert called == [(1, "clicked"), (2, "clicked")]


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

    ok, menu, sni = tray.register_tray_icon(lambda: None, lambda: None, lambda: None)

    assert ok is True
    assert menu is not None
    assert sni is not None
    assert len(watcher.calls) == 1


def test_register_tray_icon_failure(monkeypatch):
    monkeypatch.setattr(
        tray.dbus, "SessionBus", lambda: (_ for _ in ()).throw(RuntimeError("no bus"))
    )

    ok, menu, sni = tray.register_tray_icon(lambda: None, lambda: None, lambda: None)

    assert ok is False
    assert menu is None
    assert sni is None
