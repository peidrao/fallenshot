"""Fullscreen region-selection overlay — the custom screenshot picker."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gdk, GdkPixbuf, Gtk

if TYPE_CHECKING:
    from .main import FallenshotApp

SelectCallback = Callable[[GdkPixbuf.Pixbuf, int, int, int, int], None]
CancelCallback = Callable[[], None]

_DIM = 0.48  # overlay alpha when no selection
_MIN_PX = 10  # minimum selection side in window pixels


class SelectorWindow(Gtk.ApplicationWindow):
    """
    Full-screen overlay that lets the user click-drag to choose a region.

    The captured frame is displayed underneath a semi-transparent dark
    layer.  The selected rectangle is revealed at full brightness with a
    white border and size label.  Pressing ESC or choosing a region too
    small resets the selection.

    Callbacks
    ---------
    on_selected(pixbuf, x, y, w, h)
        Called with the original pixbuf and the chosen region in *image*
        coordinates once the user releases the mouse over a valid area.
    on_cancelled()
        Called when the user presses ESC.
    """

    def __init__(
        self,
        app: "FallenshotApp",
        pixbuf: GdkPixbuf.Pixbuf,
        on_selected: SelectCallback,
        on_cancelled: CancelCallback,
    ) -> None:
        super().__init__(application=app)
        self._pixbuf = pixbuf
        self._img_w = pixbuf.get_width()
        self._img_h = pixbuf.get_height()
        self._on_selected = on_selected
        self._on_cancelled = on_cancelled

        self._sel_start: tuple[float, float] | None = None
        self._sel_end: tuple[float, float] | None = None

        # Fit-to-window transform (image → window coords)
        self._scale = 1.0
        self._off_x = 0.0
        self._off_y = 0.0

        self._build()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.set_decorated(False)
        self.fullscreen()

        area = Gtk.DrawingArea()
        area.set_hexpand(True)
        area.set_vexpand(True)
        area.set_draw_func(self._on_draw)
        area.set_cursor(Gdk.Cursor.new_from_name("crosshair"))

        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._drag_begin)
        drag.connect("drag-update", self._drag_update)
        drag.connect("drag-end", self._drag_end)
        area.add_controller(drag)

        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_key)
        self.add_controller(key)

        self.set_child(area)
        self._area = area

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------

    def _update_transform(self, win_w: int, win_h: int) -> None:
        self._scale = min(win_w / self._img_w, win_h / self._img_h)
        self._off_x = (win_w - self._img_w * self._scale) / 2
        self._off_y = (win_h - self._img_h * self._scale) / 2

    def _win_to_img(self, wx: float, wy: float) -> tuple[float, float]:
        return (wx - self._off_x) / self._scale, (wy - self._off_y) / self._scale

    def _sel_rect_win(self) -> tuple[float, float, float, float] | None:
        if self._sel_start is None or self._sel_end is None:
            return None
        x1, y1 = self._sel_start
        x2, y2 = self._sel_end
        return min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1)

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _on_draw(
        self,
        _area: Gtk.DrawingArea,
        cr: cairo.Context,
        win_w: int,
        win_h: int,
    ) -> None:
        self._update_transform(win_w, win_h)

        # 1. Screenshot
        cr.save()
        cr.translate(self._off_x, self._off_y)
        cr.scale(self._scale, self._scale)
        Gdk.cairo_set_source_pixbuf(cr, self._pixbuf, 0, 0)
        cr.paint()
        cr.restore()

        # 2. Dim everything
        cr.set_source_rgba(0.0, 0.0, 0.0, _DIM)
        cr.paint()

        sel = self._sel_rect_win()
        if sel:
            rx, ry, rw, rh = sel
            if rw > 0 and rh > 0:
                self._draw_selection(cr, rx, ry, rw, rh)
        else:
            _draw_hint(
                cr, win_w, win_h, "Click and drag to select area  ·  ESC to cancel"
            )

    def _draw_selection(
        self,
        cr: cairo.Context,
        rx: float,
        ry: float,
        rw: float,
        rh: float,
    ) -> None:
        # Reveal screenshot inside selection (undo the dim)
        cr.save()
        cr.rectangle(rx, ry, rw, rh)
        cr.clip()
        cr.translate(self._off_x, self._off_y)
        cr.scale(self._scale, self._scale)
        Gdk.cairo_set_source_pixbuf(cr, self._pixbuf, 0, 0)
        cr.paint()
        cr.restore()

        # White border
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.92)
        cr.set_line_width(1.5)
        cr.rectangle(rx + 0.75, ry + 0.75, rw - 1.5, rh - 1.5)
        cr.stroke()

        # Corner handles
        cr.set_source_rgba(1.0, 1.0, 1.0, 1.0)
        hs = 6.0
        for cx, cy in ((rx, ry), (rx + rw, ry), (rx, ry + rh), (rx + rw, ry + rh)):
            cr.rectangle(cx - hs / 2, cy - hs / 2, hs, hs)
            cr.fill()

        # Subtle rule-of-thirds grid
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.25)
        cr.set_line_width(0.5)
        for t in (1 / 3, 2 / 3):
            cr.move_to(rx + rw * t, ry)
            cr.line_to(rx + rw * t, ry + rh)
            cr.move_to(rx, ry + rh * t)
            cr.line_to(rx + rw, ry + rh * t)
        cr.stroke()

        # Size label in image pixels
        if self._sel_start and self._sel_end:
            ix1, iy1 = self._win_to_img(*self._sel_start)
            ix2, iy2 = self._win_to_img(*self._sel_end)
            img_w = int(abs(ix2 - ix1))
            img_h = int(abs(iy2 - iy1))
            _draw_size_label(cr, rx, ry, rw, rh, img_w, img_h)

    # ------------------------------------------------------------------
    # Input handlers
    # ------------------------------------------------------------------

    def _drag_begin(self, _g: Gtk.GestureDrag, x: float, y: float) -> None:
        self._sel_start = (x, y)
        self._sel_end = (x, y)
        self._area.queue_draw()

    def _drag_update(self, g: Gtk.GestureDrag, dx: float, dy: float) -> None:
        ok, sx, sy = g.get_start_point()
        if ok:
            self._sel_end = (sx + dx, sy + dy)
            self._area.queue_draw()

    def _drag_end(self, _g: Gtk.GestureDrag, _dx: float, _dy: float) -> None:
        sel = self._sel_rect_win()
        if sel is None:
            return
        _, _, rw, rh = sel
        if rw < _MIN_PX or rh < _MIN_PX:
            self._sel_start = self._sel_end = None
            self._area.queue_draw()
            return
        self._confirm()

    def _on_key(
        self,
        _ctrl: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        _state: Gdk.ModifierType,
    ) -> bool:
        if keyval == Gdk.KEY_Escape:
            cb = self._on_cancelled
            self.close()
            cb()
            return True
        return False

    # ------------------------------------------------------------------
    # Confirmation
    # ------------------------------------------------------------------

    def _confirm(self) -> None:
        if self._sel_start is None or self._sel_end is None:
            return
        x1, y1 = self._win_to_img(*self._sel_start)
        x2, y2 = self._win_to_img(*self._sel_end)

        ix = int(max(0.0, min(x1, x2)))
        iy = int(max(0.0, min(y1, y2)))
        iw = int(min(abs(x2 - x1), self._img_w - ix))
        ih = int(min(abs(y2 - y1), self._img_h - iy))
        if iw < 1 or ih < 1:
            return

        cb = self._on_selected
        pixbuf = self._pixbuf
        self.close()
        cb(pixbuf, ix, iy, iw, ih)


# ------------------------------------------------------------------
# Module-level drawing helpers (no state needed)
# ------------------------------------------------------------------


def _draw_size_label(
    cr: cairo.Context,
    rx: float,
    ry: float,
    rw: float,
    rh: float,
    img_w: int,
    img_h: int,
) -> None:
    text = f" {img_w} × {img_h} "
    cr.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    cr.set_font_size(13)
    ext = cr.text_extents(text)
    lx = rx + rw - ext.width - 4
    ly = ry - 8
    if ly < ext.height + 8:
        ly = ry + rh + ext.height + 6
    cr.set_source_rgba(0.08, 0.08, 0.08, 0.88)
    cr.rectangle(lx - 3, ly - ext.height - 2, ext.width + 6, ext.height + 6)
    cr.fill()
    cr.set_source_rgba(1.0, 1.0, 1.0, 1.0)
    cr.move_to(lx, ly)
    cr.show_text(text)


def _draw_hint(cr: cairo.Context, win_w: int, win_h: int, text: str) -> None:
    cr.select_font_face("sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(15)
    ext = cr.text_extents(text)
    x = (win_w - ext.width) / 2
    y = win_h * 0.88
    cr.set_source_rgba(0.05, 0.05, 0.05, 0.82)
    cr.rectangle(x - 14, y - ext.height - 5, ext.width + 28, ext.height + 14)
    cr.fill()
    cr.set_source_rgba(1.0, 1.0, 1.0, 0.95)
    cr.move_to(x, y)
    cr.show_text(text)
