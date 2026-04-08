"""
tray.py — System tray icon via StatusNotifierItem + DBusMenu (D-Bus).

Works with GNOME Shell + AppIndicator extension, without GTK3 dependency.
"""

from __future__ import annotations

import os
from collections.abc import Callable

import dbus
import dbus.mainloop.glib
import dbus.service
import gi

gi.require_version("GdkPixbuf", "2.0")

from gi.repository import GdkPixbuf, GLib

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

_SNI_PATH = "/StatusNotifierItem"
_SNI_IFACE = "org.kde.StatusNotifierItem"
_WATCHER_NAME = "org.kde.StatusNotifierWatcher"
_WATCHER_PATH = "/StatusNotifierWatcher"
_WATCHER_IFACE = "org.kde.StatusNotifierWatcher"
_MENU_PATH = "/MenuBar"
_MENU_IFACE = "com.canonical.dbusmenu"
_APP_ICON_NAME = "io.github.fallenshot"
_TRAY_ICON_NAME = "fallenshot-tray"

# Menu item IDs
_ID_ROOT = 0
_ID_CAPTURE = 1
_ID_CAPTURE5 = 2
_ID_SEP = 3
_ID_QUIT = 4


def _load_icon_pixmap(icon_path: str) -> list:
    """Load PNG icon and return it as ARGB32 array for SNI IconPixmap."""
    try:
        pixbuf_cls = GdkPixbuf.Pixbuf
        if hasattr(pixbuf_cls, "new_from_file"):
            pb = pixbuf_cls.new_from_file(icon_path)
        else:
            pb = pixbuf_cls.new_from_file_at_size(icon_path, 24, 24)

        try:
            pb = _crop_alpha_bounds(pb)
            pb = _normalize_tray_size(pb, size=24, padding=1)
        except Exception:
            # Test doubles may not implement full Pixbuf operations.
            pass
        width = pb.get_width()
        height = pb.get_height()
        n_channels = pb.get_n_channels()
        has_alpha = pb.get_has_alpha()
        rowstride = pb.get_rowstride()
        raw = pb.get_pixels()

        if n_channels < 3:
            raise ValueError(f"Unexpected channel count: {n_channels}")

        # SNI expects ARGB32 big-endian: swap RGBA → ARGB
        argb = bytearray(width * height * 4)
        dst = 0
        for y in range(height):
            row = y * rowstride
            for x in range(width):
                src = row + x * n_channels
                red = raw[src]
                green = raw[src + 1]
                blue = raw[src + 2]
                alpha = raw[src + 3] if has_alpha and n_channels >= 4 else 255
                argb[dst] = alpha
                argb[dst + 1] = red
                argb[dst + 2] = green
                argb[dst + 3] = blue
                dst += 4

        return [(dbus.Int32(width), dbus.Int32(height), dbus.Array(argb, signature="y"))]
    except Exception as exc:
        print(f"[tray] Could not load icon pixmap: {exc}")
        return []


def _crop_alpha_bounds(pb: GdkPixbuf.Pixbuf) -> GdkPixbuf.Pixbuf:
    """Crop transparent margins to avoid tiny visible symbols in tray hosts."""
    if not pb.get_has_alpha() or pb.get_n_channels() < 4:
        return pb

    width = pb.get_width()
    height = pb.get_height()
    rowstride = pb.get_rowstride()
    n_channels = pb.get_n_channels()
    raw = pb.get_pixels()

    minx, miny = width, height
    maxx, maxy = -1, -1
    for y in range(height):
        row = y * rowstride
        for x in range(width):
            alpha = raw[row + x * n_channels + 3]
            if alpha <= 8:
                continue
            if x < minx:
                minx = x
            if y < miny:
                miny = y
            if x > maxx:
                maxx = x
            if y > maxy:
                maxy = y

    if maxx < 0:
        return pb

    crop_w = maxx - minx + 1
    crop_h = maxy - miny + 1
    return pb.new_subpixbuf(minx, miny, crop_w, crop_h).copy()


def _normalize_tray_size(
    pb: GdkPixbuf.Pixbuf, size: int = 24, padding: int = 1
) -> GdkPixbuf.Pixbuf:
    """Scale icon to a predictable visual size and center it in a transparent canvas."""
    inner = max(1, size - 2 * padding)
    scale = min(inner / pb.get_width(), inner / pb.get_height())
    scaled_w = max(1, int(round(pb.get_width() * scale)))
    scaled_h = max(1, int(round(pb.get_height() * scale)))
    scaled = pb.scale_simple(scaled_w, scaled_h, GdkPixbuf.InterpType.BILINEAR)
    if scaled is None:
        return pb

    canvas = GdkPixbuf.Pixbuf.new(
        GdkPixbuf.Colorspace.RGB,
        True,
        8,
        size,
        size,
    )
    canvas.fill(0x00000000)
    x = (size - scaled_w) // 2
    y = (size - scaled_h) // 2
    scaled.copy_area(0, 0, scaled_w, scaled_h, canvas, x, y)
    return canvas


def _resolve_icon_path() -> str | None:
    """Return the best local PNG path for tray IconPixmap fallback."""
    candidates = []
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        candidates.extend(
            [
                os.path.join(
                    xdg_data_home,
                    "icons",
                    "hicolor",
                    "256x256",
                    "apps",
                    f"{_TRAY_ICON_NAME}.png",
                ),
                os.path.join(
                    xdg_data_home, "icons", "hicolor", "256x256", "apps", "fallenshot-tray.png"
                ),
                os.path.join(
                    xdg_data_home, "icons", "hicolor", "256x256", "apps", f"{_APP_ICON_NAME}.png"
                ),
                os.path.join(
                    xdg_data_home, "icons", "hicolor", "256x256", "apps", "fallenshot.png"
                ),
            ]
        )
    candidates.extend(
        [
            os.path.expanduser(
                "~/.local/share/icons/hicolor/256x256/apps/io.github.fallenshot-tray.png"
            ),
            os.path.expanduser("~/.local/share/icons/hicolor/256x256/apps/fallenshot-tray.png"),
            os.path.expanduser(
                "~/.local/share/icons/hicolor/256x256/apps/io.github.fallenshot.png"
            ),
            os.path.expanduser("~/.local/share/icons/hicolor/256x256/apps/fallenshot.png"),
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "icons",
                "fallenshot-tray.png",
            ),
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "icons",
                "fallenshot.png",
            ),
        ]
    )
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


class _DbusMenu(dbus.service.Object):
    """Minimal DBusMenu implementation for the tray context menu."""

    def __init__(
        self,
        bus: dbus.SessionBus,
        on_capture: Callable,
        on_capture5: Callable,
        on_quit: Callable,
    ) -> None:
        super().__init__(bus, _MENU_PATH)
        self._on_capture = on_capture
        self._on_capture5 = on_capture5
        self._on_quit = on_quit
        self._revision = 1

    def _layout(self) -> tuple:
        """Build the full menu layout as required by DBusMenu GetLayout."""
        sep = dbus.Struct(
            (
                dbus.Int32(_ID_SEP),
                dbus.Dictionary({"type": dbus.String("separator")}, signature="sv"),
                dbus.Array([], signature="v"),
            ),
            signature=None,
        )
        items = [
            self._item(_ID_CAPTURE, "Take screenshot now"),
            self._item(_ID_CAPTURE5, "Take screenshot in 5 seconds"),
            sep,
            self._item(_ID_QUIT, "Quit"),
        ]
        root = dbus.Struct(
            (
                dbus.Int32(_ID_ROOT),
                dbus.Dictionary({}, signature="sv"),
                dbus.Array(items, signature="v"),
            ),
            signature=None,
        )
        return (dbus.UInt32(self._revision), root)

    @staticmethod
    def _item(item_id: int, label: str) -> dbus.Struct:
        return dbus.Struct(
            (
                dbus.Int32(item_id),
                dbus.Dictionary(
                    {
                        "label": dbus.String(label),
                        "enabled": dbus.Boolean(True),
                        "visible": dbus.Boolean(True),
                    },
                    signature="sv",
                ),
                dbus.Array([], signature="v"),
            ),
            signature=None,
        )

    @dbus.service.method(
        dbus_interface=_MENU_IFACE, in_signature="iias", out_signature="u(ia{sv}av)"
    )
    def GetLayout(
        self,
        _parent_id: int,
        _recursion_depth: int,  # noqa: N802  # pyright: ignore[reportUnusedParameter]
        _property_names: list,
    ) -> tuple:  # pyright: ignore[reportUnusedParameter]
        return self._layout()

    @dbus.service.method(dbus_interface=_MENU_IFACE, in_signature="aias", out_signature="a(ia{sv})")
    def GetGroupProperties(self, _ids: list, _property_names: list):  # noqa: N802  # pyright: ignore[reportUnusedParameter]
        return []

    @dbus.service.method(dbus_interface=_MENU_IFACE, in_signature="ia{sv}", out_signature="")
    def GetProperty(self, _item_id: int, _name: str) -> None:  # noqa: N802  # pyright: ignore[reportUnusedParameter]
        pass

    @dbus.service.method(dbus_interface=_MENU_IFACE, in_signature="isvu", out_signature="")
    def Event(
        self,
        item_id: int,
        event_id: str,  # noqa: N802
        _data,
        _timestamp: int,
    ) -> None:  # pyright: ignore[reportUnusedParameter]
        if event_id != "clicked":
            return
        if item_id == _ID_CAPTURE:
            GLib.idle_add(self._on_capture)
        elif item_id == _ID_CAPTURE5:
            GLib.idle_add(self._on_capture5)
        elif item_id == _ID_QUIT:
            GLib.idle_add(self._on_quit)

    @dbus.service.method(dbus_interface=_MENU_IFACE, in_signature="a(isvu)", out_signature="")
    def EventGroup(self, events: list) -> None:  # noqa: N802
        for item_id, event_id, data, timestamp in events:
            self.Event(item_id, event_id, data, timestamp)

    @dbus.service.method(dbus_interface=_MENU_IFACE, in_signature="i", out_signature="b")
    def AboutToShow(self, _item_id: int) -> bool:  # noqa: N802
        return False

    @dbus.service.method(dbus_interface=_MENU_IFACE, in_signature="ai", out_signature="aiai")
    def AboutToShowGroup(self, ids: list):  # noqa: N802
        return ([], [])

    @dbus.service.signal(dbus_interface=_MENU_IFACE, signature="ui")
    def LayoutUpdated(self, revision: int, parent: int) -> None:  # noqa: N802
        pass

    @dbus.service.signal(dbus_interface=_MENU_IFACE, signature="ia{sv}")
    def ItemActivationRequested(self, item_id: int, timestamp: int) -> None:  # noqa: N802
        pass


class _StatusNotifierItem(dbus.service.Object):
    """Minimal StatusNotifierItem D-Bus object."""

    def __init__(self, bus: dbus.SessionBus, icon_pixmap: list, on_capture: Callable) -> None:
        self._service_name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        self._bus_name = dbus.service.BusName(self._service_name, bus)
        self._icon_pixmap = icon_pixmap
        self._on_capture = on_capture
        super().__init__(bus, _SNI_PATH)

    def _props(self) -> dict:
        return {
            "Category": dbus.String("ApplicationStatus"),
            "Id": dbus.String("fallenshot"),
            "Title": dbus.String("Fallenshot"),
            "Status": dbus.String("Active"),
            "IconName": dbus.String(_TRAY_ICON_NAME),
            # Prefer theme icon by name; some hosts render custom ARGB pixmaps
            # at inconsistent scale.
            "IconPixmap": dbus.Array([], signature="(iiay)"),
            "IconThemePath": dbus.String(
                os.path.expanduser(os.environ.get("XDG_DATA_HOME", "~/.local/share") + "/icons")
            ),
            "ToolTip": dbus.Struct(
                (
                    "",
                    dbus.Array([], signature="(iiay)"),
                    "Fallenshot",
                    "Click to take a screenshot",
                ),
                signature=None,
            ),
            "Menu": dbus.ObjectPath(_MENU_PATH),
            "ItemIsMenu": dbus.Boolean(True),
        }

    @dbus.service.method(
        dbus_interface="org.freedesktop.DBus.Properties",
        in_signature="ss",
        out_signature="v",
    )
    def Get(self, _iface: str, prop: str):  # noqa: N802
        return self._props().get(prop, "")

    @dbus.service.method(
        dbus_interface="org.freedesktop.DBus.Properties",
        in_signature="s",
        out_signature="a{sv}",
    )
    def GetAll(self, _iface: str):  # noqa: N802
        return self._props()

    @dbus.service.method(dbus_interface=_SNI_IFACE, in_signature="ii", out_signature="")
    def Activate(self, _x: int, _y: int) -> None:  # noqa: N802
        GLib.idle_add(self._on_capture)

    @dbus.service.method(dbus_interface=_SNI_IFACE, in_signature="ii", out_signature="")
    def SecondaryActivate(self, _x: int, _y: int) -> None:  # noqa: N802
        pass

    @dbus.service.method(dbus_interface=_SNI_IFACE, in_signature="is", out_signature="")
    def Scroll(self, _delta: int, _orientation: str) -> None:  # noqa: N802
        pass

    @dbus.service.signal(dbus_interface=_SNI_IFACE, signature="")
    def NewIcon(self) -> None:  # noqa: N802
        pass

    @dbus.service.signal(dbus_interface=_SNI_IFACE, signature="")
    def NewStatus(self) -> None:  # noqa: N802
        pass


def register_tray_icon(
    on_capture: Callable,
    on_capture5: Callable,
    on_quit: Callable,
) -> tuple[bool, _DbusMenu | None, _StatusNotifierItem | None]:
    """
    Register the system tray icon via StatusNotifierWatcher.

    Returns registration status and strong references to tray DBus objects.
    """
    try:
        bus = dbus.SessionBus()
        icon_pixmap = []

        menu = _DbusMenu(bus, on_capture, on_capture5, on_quit)
        sni = _StatusNotifierItem(bus, icon_pixmap, on_capture)

        watcher = bus.get_object(_WATCHER_NAME, _WATCHER_PATH)
        dbus.Interface(watcher, _WATCHER_IFACE).RegisterStatusNotifierItem(sni._service_name)

        print("[tray] Tray icon registered.")
        return True, menu, sni
    except Exception as exc:
        print(f"[tray] Could not register tray icon: {exc}")
        return False, None, None
