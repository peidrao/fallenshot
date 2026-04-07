from __future__ import annotations

from src import screencast


def test_is_available_reflects_gst_state(monkeypatch):
    monkeypatch.setattr(screencast, "_HAS_GST", True)
    monkeypatch.setattr(screencast.Gst.ElementFactory, "find", staticmethod(lambda _name: object()))
    assert screencast.is_available() is True

    monkeypatch.setattr(screencast.Gst.ElementFactory, "find", staticmethod(lambda _name: None))
    assert screencast.is_available() is False


def test_capture_frame_unavailable_dispatches_none(monkeypatch):
    session = screencast.ScreenCastSession()
    monkeypatch.setattr("src.screencast.is_available", lambda: False)

    results = []
    monkeypatch.setattr(screencast.GLib, "idle_add", lambda fn, arg: fn(arg))

    session.capture_frame(results.append)

    assert results == [None]


def test_dispatch_clears_signals_and_calls_callback_once():
    session = screencast.ScreenCastSession()

    class Sig:
        def __init__(self):
            self.removed = False

        def remove(self):
            self.removed = True

    s1 = Sig()
    s2 = Sig()
    session._signals = [s1, s2]

    results = []
    session._callback = results.append

    session._dispatch("pix")
    assert results == ["pix"]
    assert s1.removed and s2.removed

    session._dispatch("another")
    assert results == ["pix"]


def test_on_started_without_streams_fails(monkeypatch):
    session = screencast.ScreenCastSession()

    failures = []
    session._fail = lambda reason: failures.append(reason)

    session._on_started(0, {"streams": []})

    assert failures == ["No streams in Start response"]


def test_on_started_sets_restore_token_and_opens_remote(monkeypatch):
    session = screencast.ScreenCastSession()

    opened = []
    session._open_remote = lambda node_id: opened.append(node_id)

    session._on_started(0, {"restore_token": "abc", "streams": [(55, {})]})

    assert session._restore_token == "abc"
    assert opened == [55]
