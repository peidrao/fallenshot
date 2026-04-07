from __future__ import annotations

from src.main import FallenshotApp


class DummyCast:
    def __init__(self):
        self.calls = []

    def capture_frame(self, callback):
        self.calls.append(callback)


def _make_app():
    app = FallenshotApp.__new__(FallenshotApp)
    app._cast = DummyCast()
    app._capture_in_progress = False
    app._tray_mode_enabled = False
    app.quit = lambda: None
    app.hold = lambda: None
    return app


def test_trigger_capture_schedules_when_idle(monkeypatch):
    app = _make_app()
    calls = []
    monkeypatch.setattr("src.main.GLib.timeout_add", lambda ms, fn: calls.append((ms, fn)))

    app._trigger_capture()

    assert app._capture_in_progress is True
    assert calls[0][0] == 150


def test_trigger_capture_ignores_when_in_progress(monkeypatch):
    app = _make_app()
    app._capture_in_progress = True

    calls = []
    monkeypatch.setattr("src.main.GLib.timeout_add", lambda ms, fn: calls.append((ms, fn)))

    app._trigger_capture()
    assert calls == []


def test_start_capture_calls_screencast_and_returns_false():
    app = _make_app()

    result = app._start_capture()

    assert result is False
    assert len(app._cast.calls) == 1


def test_on_frame_ready_none_resets_flag():
    app = _make_app()
    app._capture_in_progress = True

    app._on_frame_ready(None)

    assert app._capture_in_progress is False


def test_on_selection_cancelled_resets_flag():
    app = _make_app()
    app._capture_in_progress = True

    app._on_selection_cancelled()

    assert app._capture_in_progress is False


def test_on_region_selected_opens_overlay(monkeypatch):
    app = _make_app()
    app._capture_in_progress = True

    events = []

    class FakeOverlay:
        def __init__(self, _app, _pixbuf):
            events.append("init")

        def start_annotation(self, x, y, w, h):
            events.append((x, y, w, h))

        def present(self):
            events.append("present")

    monkeypatch.setattr("src.main.OverlayWindow", FakeOverlay)

    app._on_region_selected(object(), 1, 2, 3, 4)

    assert app._capture_in_progress is False
    assert events == ["init", (1, 2, 3, 4), "present"]


def test_on_frame_ready_opens_selector(monkeypatch):
    app = _make_app()

    events = []

    class FakeSelector:
        def __init__(self, _app, _pixbuf, on_selected, on_cancelled):
            events.append((on_selected, on_cancelled))

        def present(self):
            events.append("present")

    monkeypatch.setattr("src.main.SelectorWindow", FakeSelector)

    app._on_frame_ready(object())

    assert len(events) == 2
    assert events[1] == "present"
