from __future__ import annotations

import tempfile

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


def test_capture_frame_starts_watchdog(monkeypatch):
    session = screencast.ScreenCastSession()
    monkeypatch.setattr("src.screencast.is_available", lambda: True)
    started = []
    session._start_watchdog = lambda: started.append(True)
    session._create_session = lambda: None
    session.capture_frame(lambda _pix: None)
    assert started == [True]


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


def test_on_started_with_error_code_fails():
    session = screencast.ScreenCastSession()
    failures = []
    session._fail = lambda reason: failures.append(reason)

    session._on_started(2, {})
    assert failures == ["Start failed (code=2)"]


def test_on_started_sets_restore_token_and_opens_remote(monkeypatch):
    session = screencast.ScreenCastSession()

    opened = []
    session._open_remote = lambda node_id: opened.append(node_id)

    session._on_started(0, {"restore_token": "abc", "streams": [(55, {})]})

    assert session._restore_token == "abc"
    assert opened == [55]


def test_restore_token_is_persisted_and_loaded(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setenv("XDG_STATE_HOME", td)
        s1 = screencast.ScreenCastSession()
        s1._open_remote = lambda _node_id: None
        s1._on_started(0, {"restore_token": "persisted", "streams": [(1, {})]})

        s2 = screencast.ScreenCastSession()
        assert s2._restore_token == "persisted"


def test_on_new_sample_when_already_delivered_returns_ok():
    session = screencast.ScreenCastSession()
    session._frame_delivered = True
    assert session._on_new_sample(object()) == screencast.Gst.FlowReturn.OK


def test_fail_cleans_and_dispatches_none():
    session = screencast.ScreenCastSession()
    calls = []
    session._stop_pipeline = lambda: calls.append("stop")
    session._close_session = lambda: calls.append("close")
    session._dispatch = lambda pix: calls.append(("dispatch", pix))

    result = session._fail("oops")

    assert result is False
    assert calls == ["stop", "close", ("dispatch", None)]


def test_watchdog_timeout_triggers_fail():
    session = screencast.ScreenCastSession()
    failures = []
    session._request_timeout_ms = 1234
    session._fail = lambda reason: failures.append(reason) or False
    session._on_watchdog_timeout()
    assert failures == ["Request timed out after 1234 ms"]
