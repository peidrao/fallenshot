from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[1])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class _Dummy:
    def __init__(self, *args, **kwargs):
        self._signals = {}

    def __call__(self, *args, **kwargs):
        return _Dummy()

    def __getattr__(self, _name):
        def _method(*_args, **_kwargs):
            return None

        return _method

    def connect(self, name, cb, *extra):
        self._signals[name] = (cb, extra)
        return 1


class _DummyAction(_Dummy):
    @staticmethod
    def new(_name, _param):
        return _DummyAction()


class _DummyFile:
    def __init__(self, path: str):
        self._path = path

    def get_path(self):
        return self._path

    @staticmethod
    def new_for_path(path: str):
        return _DummyFile(path)


def _install_fake_cairo() -> None:
    cairo = types.ModuleType("cairo")
    cairo.LINE_CAP_ROUND = 1
    cairo.LINE_JOIN_ROUND = 1
    cairo.FONT_SLANT_NORMAL = 0
    cairo.FONT_WEIGHT_BOLD = 1
    cairo.FONT_WEIGHT_NORMAL = 0
    cairo.FORMAT_ARGB32 = 0

    class ImageSurface:
        def __init__(self, _fmt, _w, _h):
            self._writes = []

        def write_to_png(self, buffer):
            buffer.write(b"png")

    class Context(_Dummy):
        pass

    cairo.ImageSurface = ImageSurface
    cairo.Context = Context
    sys.modules["cairo"] = cairo


def _install_fake_gi() -> None:
    gi = types.ModuleType("gi")

    def require_version(_name: str, _version: str) -> None:
        return None

    gi.require_version = require_version

    repo = types.ModuleType("gi.repository")

    # GLib
    glib = types.SimpleNamespace(
        idle_add=lambda fn, *a, **k: fn(*a, **k),
        timeout_add=lambda _ms, fn, *a: fn(*a),
        source_remove=lambda _source_id: None,
        get_monotonic_time=lambda: 123456,
        Bytes=types.SimpleNamespace(new=lambda b: b),
        Error=Exception,
    )

    # Gdk
    class _ModifierType:
        CONTROL_MASK = 0x4

    gdk = types.SimpleNamespace(
        KEY_Escape=27,
        KEY_z=122,
        KEY_c=99,
        KEY_s=115,
        KEY_r=114,
        KEY_l=108,
        KEY_a=97,
        KEY_t=116,
        KEY_BackSpace=65288,
        KEY_Return=65293,
        KEY_KP_Enter=65421,
        ModifierType=_ModifierType,
        Cursor=types.SimpleNamespace(new_from_name=lambda _name: _Dummy()),
        cairo_set_source_pixbuf=lambda *_args, **_kwargs: None,
        keyval_to_unicode=lambda keyval: keyval if keyval > 0 else 0,
    )

    # GdkPixbuf
    class _Pixbuf(_Dummy):
        def __init__(self, width=100, height=80, pixels: bytes | None = None):
            super().__init__()
            self._w = width
            self._h = height
            self._pixels = pixels if pixels is not None else bytes([1, 2, 3, 4] * (width * height))

        def get_width(self):
            return self._w

        def get_height(self):
            return self._h

        def get_pixels(self):
            return self._pixels

        def convert(self, *_args, **_kwargs):
            return self

        def new_subpixbuf(self, x, y, w, h):
            return (x, y, w, h)

        @staticmethod
        def new_from_file_at_size(_path, w, h):
            return _Pixbuf(w, h, bytes([10, 20, 30, 40] * (w * h)))

        @staticmethod
        def new_from_bytes(_bytes, _colorspace, _alpha, _bpc, w, h, _rowstride):
            return _Pixbuf(w, h)

    class _PixbufLoader(_Dummy):
        @staticmethod
        def new_with_type(_kind):
            return _PixbufLoader()

        def write(self, _data):
            return None

        def close(self):
            return None

        def get_pixbuf(self):
            return _Pixbuf()

    gdkpixbuf = types.SimpleNamespace(
        Pixbuf=_Pixbuf,
        PixbufLoader=_PixbufLoader,
        Colorspace=types.SimpleNamespace(RGB=0),
    )

    # Gio
    gio = types.SimpleNamespace(
        File=_DummyFile,
        SimpleAction=_DummyAction,
        ApplicationFlags=types.SimpleNamespace(FLAGS_NONE=0),
    )

    # Gtk
    class _Application(_Dummy):
        def run(self, _argv):
            return 0

        def add_action(self, _a):
            return None

        def set_accels_for_action(self, _name, _accels):
            return None

        def hold(self):
            return None

    class _Dialog(_Dummy):
        def __init__(self, *args, **kwargs):
            super().__init__()
            self._file = _DummyFile("/tmp/out")

        def add_button(self, *_args):
            return None

        def set_current_name(self, _name):
            return None

        def set_current_folder(self, _folder):
            return None

        def add_filter(self, _f):
            return None

        def get_file(self):
            return self._file

        def present(self):
            return None

        def destroy(self):
            return None

    class _FileFilter(_Dummy):
        def set_name(self, _name):
            return None

        def add_mime_type(self, _mime):
            return None

    class _StyleContext:
        @staticmethod
        def add_provider_for_display(*_args, **_kwargs):
            return None

    gtk = types.SimpleNamespace(
        Application=_Application,
        ApplicationWindow=type("ApplicationWindow", (_Dummy,), {}),
        DrawingArea=type("DrawingArea", (_Dummy,), {}),
        GestureDrag=type("GestureDrag", (_Dummy,), {}),
        EventControllerKey=type("EventControllerKey", (_Dummy,), {}),
        Overlay=type("Overlay", (_Dummy,), {}),
        Box=type("Box", (_Dummy,), {}),
        Button=type("Button", (_Dummy,), {}),
        Separator=type("Separator", (_Dummy,), {}),
        Label=type("Label", (_Dummy,), {}),
        FileChooserDialog=_Dialog,
        FileFilter=_FileFilter,
        CssProvider=type("CssProvider", (_Dummy,), {}),
        StyleContext=_StyleContext,
        Orientation=types.SimpleNamespace(HORIZONTAL=0, VERTICAL=1),
        Align=types.SimpleNamespace(CENTER=0, END=1, START=2),
        FileChooserAction=types.SimpleNamespace(SAVE=0),
        ResponseType=types.SimpleNamespace(CANCEL=0, ACCEPT=1),
        STYLE_PROVIDER_PRIORITY_APPLICATION=0,
    )

    # Gst
    class _FakeElementFactory:
        @staticmethod
        def find(_name):
            return object()

    class _FakePipeline(_Dummy):
        def get_by_name(self, _name):
            return _Dummy()

        def set_state(self, _state):
            return None

    gst = types.SimpleNamespace(
        init=lambda _x: None,
        ElementFactory=_FakeElementFactory,
        parse_launch=lambda _desc: _FakePipeline(),
        State=types.SimpleNamespace(PLAYING=1, NULL=0),
        FlowReturn=types.SimpleNamespace(OK=0),
        MapFlags=types.SimpleNamespace(READ=1),
        Pipeline=_FakePipeline,
        Element=object,
        Sample=object,
    )

    repo.GLib = glib
    repo.Gdk = gdk
    repo.GdkPixbuf = gdkpixbuf
    repo.Gio = gio
    repo.Gtk = gtk
    repo.Gst = gst

    sys.modules["gi"] = gi
    sys.modules["gi.repository"] = repo


def _install_fake_dbus() -> None:
    dbus = types.ModuleType("dbus")

    class _FakeSignal:
        def __init__(self):
            self.removed = False

        def remove(self):
            self.removed = True

    class _FakeObj:
        def connect_to_signal(self, _name, _handler):
            return _FakeSignal()

    class _SessionBus:
        def get_object(self, *_args, **_kwargs):
            return _FakeObj()

    def _identity(value=None, *args, **kwargs):
        return value

    def _array(value, signature=None):
        return list(value)

    class _ServiceModule(types.ModuleType):
        class Object:
            def __init__(self, _bus=None, _path=None):
                pass

        class BusName:
            def __init__(self, _name, _bus):
                pass

        @staticmethod
        def method(*_args, **_kwargs):
            def deco(fn):
                return fn

            return deco

        @staticmethod
        def signal(*_args, **_kwargs):
            def deco(fn):
                return fn

            return deco

    mainloop = types.ModuleType("dbus.mainloop")
    glib = types.ModuleType("dbus.mainloop.glib")
    glib.DBusGMainLoop = lambda *args, **kwargs: None
    mainloop.glib = glib

    dbus.SessionBus = _SessionBus
    dbus.Interface = lambda obj, _iface: obj
    dbus.String = _identity
    dbus.UInt32 = _identity
    dbus.Boolean = _identity
    dbus.Int32 = _identity
    dbus.Array = _array
    dbus.Dictionary = lambda value, signature=None: dict(value)
    dbus.Struct = lambda value, signature=None: tuple(value)
    dbus.ObjectPath = _identity
    dbus.DBusException = Exception
    dbus.mainloop = mainloop

    service = _ServiceModule("dbus.service")
    dbus.service = service

    sys.modules["dbus"] = dbus
    sys.modules["dbus.service"] = service
    sys.modules["dbus.mainloop"] = mainloop
    sys.modules["dbus.mainloop.glib"] = glib


def pytest_configure() -> None:
    _install_fake_cairo()
    _install_fake_gi()
    _install_fake_dbus()
