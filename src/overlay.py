"""Annotation overlay window rendered on top of a captured screenshot."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

import cairo
import gi


gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

from .drawing import Shape, TextAnnotation, make_shape
from .export import ExportManager

if TYPE_CHECKING:
    from .main import FallenshotApp

Color = tuple[float, float, float, float]
Region = tuple[int, int, int, int]

PALETTE: list[Color] = [
    (1.0, 0.18, 0.18, 1.0),
    (0.1, 0.85, 0.3, 1.0),
    (0.2, 0.55, 1.0, 1.0),
    (1.0, 0.85, 0.0, 1.0),
    (1.0, 1.0, 1.0, 1.0),
    (0.0, 0.0, 0.0, 1.0),
]
PALETTE_NAMES = ["Red", "Green", "Blue", "Yellow", "White", "Black"]

TOOLBAR_CSS = b"""
window { background: #000; }
.toolbar-box {
    background: rgba(20, 20, 24, 0.96);
    border-radius: 12px;
    padding: 8px 12px;
    border: 1px solid rgba(255,255,255,0.15);
}
.toolbar-box button {
    min-width: 40px;
    min-height: 40px;
    border-radius: 8px;
    color: white;
    background: transparent;
    border: none;
    font-size: 15px;
    padding: 4px 8px;
}
.toolbar-box button:hover {
    background: rgba(255,255,255,0.15);
}
.toolbar-box button.tool-active {
    background: rgba(70,120,255,0.8);
    border: 1px solid rgba(100,160,255,0.6);
}
.toolbar-box separator {
    background: rgba(255,255,255,0.18);
    min-width: 1px;
    margin: 6px 3px;
}
"""


class OverlayWindow(Gtk.ApplicationWindow):
    """Fullscreen annotation surface backed by an original screenshot pixbuf."""

    TOOLS = ["rect", "line", "arrow", "text"]
    TOOL_ICONS = {"rect": "⬜", "line": "╱", "arrow": "➜", "text": "T"}
    TOOL_TIPS = {
        "rect": "Rectangle (R)",
        "line": "Line (L)",
        "arrow": "Arrow (A)",
        "text": "Text (T)",
    }

    def __init__(
        self, app: "FallenshotApp", screenshot_pixbuf: GdkPixbuf.Pixbuf
    ) -> None:
        """
        Build the overlay window around the provided screenshot image.

        Args:
            app: Parent GTK application.
            screenshot_pixbuf: Full screenshot image loaded from the portal.
        """
        super().__init__(application=app)

        self._screenshot = screenshot_pixbuf
        self._image_width = screenshot_pixbuf.get_width()
        self._image_height = screenshot_pixbuf.get_height()

        self._region_of_interest: Region | None = None

        self._active_tool = "rect"
        self._active_color_index = 0
        self._stroke_width = 2.5

        self._shapes: list[Shape] = []
        self._undo_history: list[list[Shape]] = []
        self._active_shape: Shape | None = None

        self._scale = 1.0
        self._offset_x = 0.0
        self._offset_y = 0.0
        self._roi_x = 0
        self._roi_y = 0

        self._export_manager = ExportManager(self)

        self._build_window()
        self._build_toolbar()
        self._wire_input()
        self._wire_keyboard()

    def start_annotation(self, x: int, y: int, width: int, height: int) -> None:
        """
        Start annotation mode for the selected image region.

        Args:
            x: Region origin X in image coordinates.
            y: Region origin Y in image coordinates.
            width: Region width in pixels.
            height: Region height in pixels.
        """
        bounded_width = min(width, self._image_width - x)
        bounded_height = min(height, self._image_height - y)
        if bounded_width <= 0 or bounded_height <= 0:
            raise ValueError("Invalid annotation region.")

        self._region_of_interest = (x, y, bounded_width, bounded_height)
        self.maximize()
        self._drawing_area.queue_draw()

    def _build_window(self) -> None:
        self.set_decorated(False)
        self.set_resizable(True)

        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(TOOLBAR_CSS)
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        self._root_overlay = Gtk.Overlay()
        self._root_overlay.set_hexpand(True)
        self._root_overlay.set_vexpand(True)

        self._drawing_area = Gtk.DrawingArea()
        self._drawing_area.set_hexpand(True)
        self._drawing_area.set_vexpand(True)
        self._drawing_area.set_draw_func(self._on_draw)

        self._root_overlay.set_child(self._drawing_area)
        self.set_child(self._root_overlay)

    def _build_toolbar(self) -> None:
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        toolbar.add_css_class("toolbar-box")
        toolbar.set_halign(Gtk.Align.CENTER)
        toolbar.set_valign(Gtk.Align.END)
        toolbar.set_margin_bottom(28)

        self._tool_buttons: dict[str, Gtk.Button] = {}
        for tool in self.TOOLS:
            tool_button = Gtk.Button(label=self.TOOL_ICONS[tool])
            tool_button.set_tooltip_text(self.TOOL_TIPS[tool])
            tool_button.connect("clicked", self._on_tool_click, tool)
            toolbar.append(tool_button)
            self._tool_buttons[tool] = tool_button
        self._refresh_tool_buttons()

        toolbar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        for label, width, tooltip in (("─", 1.5, "Thin"), ("━", 4.0, "Thick")):
            width_button = Gtk.Button(label=label)
            width_button.set_tooltip_text(tooltip)
            width_button.connect(
                "clicked",
                lambda _, selected_width=width: self._set_stroke_width(selected_width),
            )
            toolbar.append(width_button)

        toolbar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        self._color_label = Gtk.Label()
        self._color_label.set_margin_start(4)
        self._color_label.set_margin_end(4)

        color_button = Gtk.Button()
        color_button.set_child(self._color_label)
        color_button.set_tooltip_text("Next color (C)")
        color_button.connect("clicked", lambda _: self._cycle_color())
        toolbar.append(color_button)
        self._update_color_label()

        toolbar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        undo_button = Gtk.Button(label="↩ Undo")
        undo_button.set_tooltip_text("Ctrl+Z")
        undo_button.connect("clicked", lambda _: self._undo())
        toolbar.append(undo_button)

        toolbar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        copy_button = Gtk.Button(label="📋 Copy")
        copy_button.set_tooltip_text("Ctrl+C")
        copy_button.connect("clicked", lambda _: self._copy_selection())
        toolbar.append(copy_button)

        save_button = Gtk.Button(label="💾 Save")
        save_button.set_tooltip_text("Ctrl+S")
        save_button.connect("clicked", lambda _: self._save_selection())
        toolbar.append(save_button)

        toolbar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        exit_button = Gtk.Button(label="✕ Exit")
        exit_button.set_tooltip_text("Esc")
        exit_button.connect("clicked", lambda _: self.close())
        toolbar.append(exit_button)

        self._toolbar = toolbar
        self._root_overlay.add_overlay(toolbar)

    def _wire_input(self) -> None:
        drag_controller = Gtk.GestureDrag()
        drag_controller.connect("drag-begin", self._drag_begin)
        drag_controller.connect("drag-update", self._drag_update)
        drag_controller.connect("drag-end", self._drag_end)
        self._drawing_area.add_controller(drag_controller)

    def _wire_keyboard(self) -> None:
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_controller)

    def _update_transform(self, window_width: int, window_height: int) -> None:
        if self._region_of_interest is None:
            return

        roi_x, roi_y, roi_width, roi_height = self._region_of_interest
        self._scale = min(window_width / roi_width, window_height / roi_height)
        self._offset_x = (window_width - roi_width * self._scale) / 2
        self._offset_y = (window_height - roi_height * self._scale) / 2
        self._roi_x = roi_x
        self._roi_y = roi_y

    def _window_to_image(self, window_x: float, window_y: float) -> tuple[float, float]:
        image_x = (window_x - self._offset_x) / self._scale + self._roi_x
        image_y = (window_y - self._offset_y) / self._scale + self._roi_y
        return image_x, image_y

    def _on_draw(
        self,
        _area: Gtk.DrawingArea,
        context: cairo.Context,
        width: int,
        height: int,
    ) -> None:
        if self._region_of_interest is None:
            return

        self._update_transform(width, height)
        roi_x, roi_y, roi_width, roi_height = self._region_of_interest

        context.save()
        context.translate(self._offset_x, self._offset_y)
        context.scale(self._scale, self._scale)
        Gdk.cairo_set_source_pixbuf(context, self._screenshot, -roi_x, -roi_y)
        context.paint()
        context.restore()

        context.save()
        context.translate(self._offset_x, self._offset_y)
        context.scale(self._scale, self._scale)
        context.translate(-roi_x, -roi_y)
        for shape in self._shapes:
            shape.draw(context)
        if self._active_shape is not None:
            self._active_shape.draw(context)
        context.restore()

    def _commit_active_text(self) -> None:
        """Commit or discard the in-progress TextAnnotation when leaving text mode."""
        if not isinstance(self._active_shape, TextAnnotation):
            return
        if self._active_shape.text:
            self._shapes.append(self._active_shape)
        elif self._undo_history:
            # No text was typed — discard the undo snapshot pushed at drag-begin
            self._undo_history.pop()
        self._active_shape = None

    def _drag_begin(
        self, _gesture: Gtk.GestureDrag, start_x: float, start_y: float
    ) -> None:
        # If a text annotation is already in progress, commit it before starting a new shape
        self._commit_active_text()

        image_x, image_y = self._window_to_image(start_x, start_y)
        color = PALETTE[self._active_color_index]

        self._push_undo_state()
        if self._active_tool == "text":
            self._active_shape = TextAnnotation(
                image_x, image_y, color=color, width=self._stroke_width
            )
        else:
            self._active_shape = make_shape(
                self._active_tool,
                image_x,
                image_y,
                color,
                self._stroke_width,
            )
        self._drawing_area.queue_draw()

    def _drag_update(
        self, gesture: Gtk.GestureDrag, delta_x: float, delta_y: float
    ) -> None:
        _active, start_x, start_y = gesture.get_start_point()
        if start_x is None or start_y is None:
            return

        image_x, image_y = self._window_to_image(start_x + delta_x, start_y + delta_y)
        if self._active_shape is not None:
            self._active_shape.update(image_x, image_y)
        self._drawing_area.queue_draw()

    def _drag_end(
        self, _gesture: Gtk.GestureDrag, _delta_x: float, _delta_y: float
    ) -> None:
        if self._active_shape is not None and self._active_tool != "text":
            self._shapes.append(self._active_shape)
            self._active_shape = None
        self._drawing_area.queue_draw()

    def _on_key_pressed(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        state: Gdk.ModifierType,
    ) -> bool:
        ctrl_pressed = bool(state & Gdk.ModifierType.CONTROL_MASK)

        if keyval == Gdk.KEY_Escape:
            self.close()
            return True

        if ctrl_pressed:
            if keyval == Gdk.KEY_z:
                self._undo()
                return True
            if keyval == Gdk.KEY_c:
                self._copy_selection()
                return True
            if keyval == Gdk.KEY_s:
                self._save_selection()
                return True

        tool_shortcuts = {
            Gdk.KEY_r: "rect",
            Gdk.KEY_l: "line",
            Gdk.KEY_a: "arrow",
            Gdk.KEY_t: "text",
        }
        selected_tool = tool_shortcuts.get(keyval)
        if selected_tool is not None:
            self._set_tool(selected_tool)
            return True

        if keyval == Gdk.KEY_c:
            self._cycle_color()
            return True

        if self._active_tool == "text" and isinstance(
            self._active_shape, TextAnnotation
        ):
            return self._handle_text_input(keyval)

        return False

    def _handle_text_input(self, keyval: int) -> bool:
        if self._active_shape is None or not isinstance(
            self._active_shape, TextAnnotation
        ):
            return False

        if keyval == Gdk.KEY_BackSpace:
            self._active_shape.text = self._active_shape.text[:-1]
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self._shapes.append(self._active_shape)
            self._active_shape = None
        else:
            unicode_codepoint = Gdk.keyval_to_unicode(keyval)
            character = chr(unicode_codepoint) if unicode_codepoint else ""
            if not character or not character.isprintable():
                return False
            self._active_shape.text += character

        self._drawing_area.queue_draw()
        return True

    def _set_tool(self, tool: str) -> None:
        self._commit_active_text()
        self._active_tool = tool
        self._refresh_tool_buttons()

    def _refresh_tool_buttons(self) -> None:
        for tool, button in self._tool_buttons.items():
            if tool == self._active_tool:
                button.add_css_class("tool-active")
            else:
                button.remove_css_class("tool-active")

    def _on_tool_click(self, _button: Gtk.Button, tool: str) -> None:
        self._set_tool(tool)

    def _set_stroke_width(self, width: float) -> None:
        self._stroke_width = width

    def _cycle_color(self) -> None:
        self._active_color_index = (self._active_color_index + 1) % len(PALETTE)
        self._update_color_label()

    def _update_color_label(self) -> None:
        red, green, blue, _alpha = PALETTE[self._active_color_index]
        hex_color = f"#{int(red * 255):02x}{int(green * 255):02x}{int(blue * 255):02x}"
        color_name = PALETTE_NAMES[self._active_color_index]
        self._color_label.set_markup(f'<span color="{hex_color}">●</span> {color_name}')

    def _push_undo_state(self) -> None:
        self._undo_history.append([copy.copy(shape) for shape in self._shapes])

    def _undo(self) -> None:
        if not self._undo_history:
            return
        self._shapes = self._undo_history.pop()
        self._active_shape = None
        self._drawing_area.queue_draw()

    def _render_to_surface(self) -> cairo.ImageSurface | None:
        if self._region_of_interest is None:
            return None

        roi_x, roi_y, roi_width, roi_height = self._region_of_interest
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, roi_width, roi_height)
        context = cairo.Context(surface)

        context.translate(-roi_x, -roi_y)
        Gdk.cairo_set_source_pixbuf(context, self._screenshot, 0, 0)
        context.paint()

        for shape in self._shapes:
            shape.draw(context)

        return surface

    def _copy_selection(self) -> None:
        surface = self._render_to_surface()
        if surface is None or self._region_of_interest is None:
            return

        roi_width, roi_height = self._region_of_interest[2], self._region_of_interest[3]
        copied = self._export_manager.copy_surface_to_clipboard(
            surface, (0, 0, roi_width, roi_height)
        )
        if copied:
            self._show_toast("Copied to clipboard.")

    def _save_selection(self) -> None:
        surface = self._render_to_surface()
        if surface is None or self._region_of_interest is None:
            return

        roi_width, roi_height = self._region_of_interest[2], self._region_of_interest[3]
        self._export_manager.save_surface_to_file(
            surface,
            (0, 0, roi_width, roi_height),
            on_done=self._on_save_completed,
        )

    def _on_save_completed(self, path: str | None) -> None:
        if path is None:
            return
        print(f"[fallenshot] Saved: {path}")
        self.close()

    def _show_toast(self, message: str) -> None:
        print(f"[fallenshot] {message}")
        toast_label = Gtk.Label(label=message)
        toast_label.add_css_class("toolbar-box")
        toast_label.set_halign(Gtk.Align.CENTER)
        toast_label.set_valign(Gtk.Align.START)
        toast_label.set_margin_top(20)

        self._root_overlay.add_overlay(toast_label)

        def remove_toast() -> bool:
            self._root_overlay.remove_overlay(toast_label)
            return False

        GLib.timeout_add(2500, remove_toast)
