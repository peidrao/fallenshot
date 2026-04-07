"""ScreenCast portal → PipeWire → single-frame GdkPixbuf."""

from __future__ import annotations

import os
from typing import Callable

import dbus
import dbus.mainloop.glib
import gi

gi.require_version("GdkPixbuf", "2.0")

_HAS_GST = False
try:
    gi.require_version("Gst", "1.0")
    from gi.repository import Gst
    Gst.init(None)
    _HAS_GST = True
except Exception:
    pass

from gi.repository import GdkPixbuf, GLib

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

_PORTAL      = "org.freedesktop.portal.Desktop"
_PORTAL_PATH = "/org/freedesktop/portal/desktop"
_SC_IFACE    = "org.freedesktop.portal.ScreenCast"
_SESS_IFACE  = "org.freedesktop.portal.Session"
_DEFAULT_CAPTURE_WARMUP_MS = 350
_DEFAULT_REQUEST_TIMEOUT_MS = 12000

FrameCallback = Callable[[GdkPixbuf.Pixbuf | None], None]


def is_available() -> bool:
    """Return True if the PipeWire GStreamer source element is present."""
    return _HAS_GST and Gst.ElementFactory.find("pipewiresrc") is not None


class ScreenCastSession:
    """
    Drives a ScreenCast portal session and delivers one captured frame.

    Flow: CreateSession → SelectSources → Start → OpenPipeWireRemote
          → GStreamer pipeline → first sample → GdkPixbuf callback.

    A ``restore_token`` is kept in memory so that after the first run
    (which requires GNOME's "Choose what to share" dialog) subsequent
    captures within the same process skip the dialog entirely.
    """

    def __init__(self) -> None:
        self._bus = dbus.SessionBus()
        self._session_path: str | None = None
        self._restore_token: str | None = self._load_restore_token()
        self._callback: FrameCallback | None = None
        self._pipeline: Gst.Pipeline | None = None
        self._signals: list = []
        self._frame_delivered = False
        self._capture_warmup_ms = self._read_capture_warmup_ms()
        self._request_timeout_ms = self._read_request_timeout_ms()
        self._watchdog_source_id: int | None = None

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def capture_frame(self, callback: FrameCallback) -> None:
        """Start the capture pipeline and call *callback* with the frame."""
        if not is_available():
            print("[screencast] pipewiresrc not found — install gstreamer1.0-pipewire.")
            GLib.idle_add(callback, None)
            return
        self._callback = callback
        self._frame_delivered = False
        self._start_watchdog()
        self._create_session()

    # ------------------------------------------------------------------
    # Portal handshake
    # ------------------------------------------------------------------

    def _token(self) -> str:
        return f"fs{GLib.get_monotonic_time()}"

    @staticmethod
    def _read_capture_warmup_ms() -> int:
        raw = os.environ.get("FALLENSHOT_CAPTURE_WARMUP_MS", str(_DEFAULT_CAPTURE_WARMUP_MS))
        try:
            value = int(raw)
        except ValueError:
            return _DEFAULT_CAPTURE_WARMUP_MS
        return max(0, value)

    @staticmethod
    def _read_request_timeout_ms() -> int:
        raw = os.environ.get("FALLENSHOT_REQUEST_TIMEOUT_MS", str(_DEFAULT_REQUEST_TIMEOUT_MS))
        try:
            value = int(raw)
        except ValueError:
            return _DEFAULT_REQUEST_TIMEOUT_MS
        return max(1000, value)

    @staticmethod
    def _restore_token_path() -> str:
        state_home = os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state"))
        return os.path.join(state_home, "fallenshot", "screencast_restore_token")

    def _load_restore_token(self) -> str | None:
        path = self._restore_token_path()
        try:
            with open(path, "r", encoding="utf-8") as token_file:
                token = token_file.read().strip()
                return token or None
        except OSError:
            return None

    def _save_restore_token(self, token: str) -> None:
        path = self._restore_token_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as token_file:
                token_file.write(token)
        except OSError as exc:
            print(f"[screencast] Could not persist restore token: {exc}")

    def _watch(self, path: str, handler: Callable) -> None:
        req = self._bus.get_object(_PORTAL, path)
        self._signals.append(req.connect_to_signal("Response", handler))

    def _start_watchdog(self) -> None:
        self._stop_watchdog()
        self._watchdog_source_id = GLib.timeout_add(
            self._request_timeout_ms,
            self._on_watchdog_timeout,
        )

    def _stop_watchdog(self) -> None:
        if self._watchdog_source_id is not None:
            try:
                GLib.source_remove(self._watchdog_source_id)
            except Exception:
                pass
            self._watchdog_source_id = None

    def _on_watchdog_timeout(self) -> bool:
        self._watchdog_source_id = None
        return self._fail(f"Request timed out after {self._request_timeout_ms} ms")

    def _sc(self) -> dbus.Interface:
        return dbus.Interface(self._bus.get_object(_PORTAL, _PORTAL_PATH), _SC_IFACE)

    def _create_session(self) -> None:
        path = self._sc().CreateSession({
            "handle_token":         dbus.String(self._token(), variant_level=1),
            "session_handle_token": dbus.String(self._token(), variant_level=1),
        })
        self._watch(path, self._on_session_created)

    def _on_session_created(self, code: int, results: dict) -> None:
        if code != 0:
            return self._fail(f"CreateSession failed (code={code})")
        self._session_path = str(results["session_handle"])
        self._select_sources()

    def _select_sources(self) -> None:
        opts: dict = {
            "handle_token": dbus.String(self._token(), variant_level=1),
            "types":        dbus.UInt32(1, variant_level=1),   # Monitor
            "multiple":     dbus.Boolean(False, variant_level=1),
            "cursor_mode":  dbus.UInt32(2, variant_level=1),   # embedded
            "persist_mode": dbus.UInt32(2, variant_level=1),   # cross-session token
        }
        if self._restore_token:
            opts["restore_token"] = dbus.String(self._restore_token, variant_level=1)
        path = self._sc().SelectSources(dbus.ObjectPath(self._session_path), opts)
        self._watch(path, self._on_sources_selected)

    def _on_sources_selected(self, code: int, results: dict) -> None:
        if code != 0:
            return self._fail(f"SelectSources failed (code={code})")
        self._start_cast()

    def _start_cast(self) -> None:
        path = self._sc().Start(
            dbus.ObjectPath(self._session_path),
            "",
            {"handle_token": dbus.String(self._token(), variant_level=1)},
        )
        self._watch(path, self._on_started)

    def _on_started(self, code: int, results: dict) -> None:
        if code != 0:
            return self._fail(f"Start failed (code={code})")
        if "restore_token" in results:
            self._restore_token = str(results["restore_token"])
            self._save_restore_token(self._restore_token)
        streams = results.get("streams", [])
        if not streams:
            return self._fail("No streams in Start response")
        node_id = int(streams[0][0])
        GLib.timeout_add(self._capture_warmup_ms, self._open_remote_after_warmup, node_id)

    def _open_remote_after_warmup(self, node_id: int) -> bool:
        self._open_remote(node_id)
        return False

    # ------------------------------------------------------------------
    # PipeWire / GStreamer
    # ------------------------------------------------------------------

    def _open_remote(self, node_id: int) -> None:
        fd_obj = self._sc().OpenPipeWireRemote(dbus.ObjectPath(self._session_path), {})
        fd: int = fd_obj.take()
        self._build_pipeline(fd, node_id)

    def _build_pipeline(self, fd: int, node_id: int) -> None:
        desc = (
            f"pipewiresrc fd={fd} path={node_id} always-copy=true do-timestamp=true ! "
            "videoconvert ! "
            "video/x-raw,format=RGBA ! "
            "appsink name=sink max-buffers=1 drop=true sync=false emit-signals=true"
        )
        try:
            self._pipeline = Gst.parse_launch(desc)
        except GLib.Error as exc:
            return self._fail(f"Pipeline error: {exc}")

        sink = self._pipeline.get_by_name("sink")
        sink.connect("new-sample", self._on_new_sample)
        self._pipeline.set_state(Gst.State.PLAYING)

    def _on_new_sample(self, appsink: Gst.Element) -> Gst.FlowReturn:
        """Called from a GStreamer thread — hand off to GLib main loop."""
        if self._frame_delivered:
            return Gst.FlowReturn.OK
        self._frame_delivered = True
        sample = appsink.emit("pull-sample")
        if sample:
            GLib.idle_add(self._deliver_sample, sample)
        else:
            GLib.idle_add(self._fail, "pull-sample returned None")
        return Gst.FlowReturn.OK

    def _deliver_sample(self, sample: Gst.Sample) -> bool:
        """Decode the GStreamer sample into a GdkPixbuf on the main thread."""
        self._stop_pipeline()
        self._close_session()

        pixbuf: GdkPixbuf.Pixbuf | None = None
        try:
            caps = sample.get_caps()
            struct = caps.get_structure(0)
            width: int = struct.get_value("width")
            height: int = struct.get_value("height")
            buf = sample.get_buffer()
            ok, mapinfo = buf.map(Gst.MapFlags.READ)
            if ok:
                # GLib.Bytes keeps the data alive for the pixbuf's lifetime
                gbytes = GLib.Bytes.new(bytes(mapinfo.data))
                buf.unmap(mapinfo)
                pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(
                    gbytes,
                    GdkPixbuf.Colorspace.RGB,
                    True,   # has_alpha — RGBA format
                    8,
                    width,
                    height,
                    width * 4,
                )
            else:
                print("[screencast] Buffer map failed.")
        except Exception as exc:
            print(f"[screencast] Frame decode error: {exc}")

        self._dispatch(pixbuf)
        return False

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def _stop_pipeline(self) -> None:
        if self._pipeline:
            self._pipeline.set_state(Gst.State.NULL)
            self._pipeline = None

    def _close_session(self) -> None:
        if self._session_path:
            try:
                sess = self._bus.get_object(_PORTAL, self._session_path)
                dbus.Interface(sess, _SESS_IFACE).Close()
            except dbus.DBusException:
                pass
            self._session_path = None

    def _fail(self, reason: str) -> bool:
        """Log failure, clean up, and deliver None to the callback."""
        print(f"[screencast] {reason}")
        self._stop_pipeline()
        self._close_session()
        self._dispatch(None)
        return False  # safe return value for GLib.idle_add

    def _dispatch(self, pixbuf: GdkPixbuf.Pixbuf | None) -> None:
        self._stop_watchdog()
        for sig in self._signals:
            try:
                sig.remove()
            except Exception:
                pass
        self._signals.clear()
        if self._callback:
            cb, self._callback = self._callback, None
            cb(pixbuf)
