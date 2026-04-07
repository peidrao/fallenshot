"""
overlay.py — Janela de anotação com tamanho do screenshot selecionado.

A janela abre com o tamanho exato da área capturada.
Coordenadas são 1:1 com a imagem — sem scaling.
"""

import math
import os
import cairo

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

from .drawing import make_shape, TextAnnotation
from .export import ExportManager

COLORS = [
    (1.0, 0.18, 0.18, 1.0),  # vermelho
    (0.1,  0.85, 0.3,  1.0),  # verde
    (0.2,  0.55, 1.0,  1.0),  # azul
    (1.0,  0.85, 0.0,  1.0),  # amarelo
    (1.0,  1.0,  1.0,  1.0),  # branco
    (0.0,  0.0,  0.0,  1.0),  # preto
]
COLOR_NAMES = ["Vermelho", "Verde", "Azul", "Amarelo", "Branco", "Preto"]

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

    TOOLS      = ["rect", "line", "arrow", "text"]
    TOOL_ICONS = {"rect": "⬜", "line": "╱", "arrow": "➜", "text": "T"}
    TOOL_TIPS  = {
        "rect":  "Retângulo (R)",
        "line":  "Linha (L)",
        "arrow": "Seta (A)",
        "text":  "Texto (T)",
    }

    def __init__(self, app, screenshot_pixbuf: GdkPixbuf.Pixbuf):
        super().__init__(application=app)

        self._screenshot = screenshot_pixbuf
        self._img_w = screenshot_pixbuf.get_width()
        self._img_h = screenshot_pixbuf.get_height()

        # Região de interesse (x, y, w, h) dentro da imagem
        self._roi: tuple | None = None

        self._current_tool      = "rect"
        self._current_color_idx = 0
        self._stroke_width      = 2.5
        self._shapes            = []
        self._undo_history      = []
        self._active_shape      = None

        # Transform (calculado em _on_draw)
        self._scale    = 1.0
        self._offset_x = 0.0
        self._offset_y = 0.0
        self._roi_x    = 0
        self._roi_y    = 0

        self._exporter = ExportManager(self)
        self._build_window()
        self._build_toolbar()
        self._wire_input()
        self._wire_keyboard()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_window(self):
        self.set_decorated(False)
        self.set_resizable(True)

        css = Gtk.CssProvider()
        css.load_from_data(TOOLBAR_CSS)
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self._root = Gtk.Overlay()
        self._root.set_hexpand(True)
        self._root.set_vexpand(True)

        self._drawing = Gtk.DrawingArea()
        self._drawing.set_hexpand(True)
        self._drawing.set_vexpand(True)
        self._drawing.set_draw_func(self._on_draw)

        self._root.set_child(self._drawing)
        self.set_child(self._root)

    def _build_toolbar(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        bar.add_css_class("toolbar-box")
        bar.set_halign(Gtk.Align.CENTER)
        bar.set_valign(Gtk.Align.END)
        bar.set_margin_bottom(28)

        self._tool_buttons = {}
        for tool in self.TOOLS:
            btn = Gtk.Button(label=self.TOOL_ICONS[tool])
            btn.set_tooltip_text(self.TOOL_TIPS[tool])
            btn.connect("clicked", self._on_tool_click, tool)
            bar.append(btn)
            self._tool_buttons[tool] = btn
        self._refresh_tool_buttons()

        bar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        for label, width, tip in [("─", 1.5, "Fino"), ("━", 4.0, "Grosso")]:
            b = Gtk.Button(label=label)
            b.set_tooltip_text(tip)
            b.connect("clicked", lambda _, w=width: self._set_width(w))
            bar.append(b)

        bar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        self._color_label = Gtk.Label(label="● Vermelho")
        self._color_label.set_margin_start(4)
        self._color_label.set_margin_end(4)
        color_btn = Gtk.Button()
        color_btn.set_child(self._color_label)
        color_btn.set_tooltip_text("Próxima cor (C)")
        color_btn.connect("clicked", lambda _: self._cycle_color())
        bar.append(color_btn)

        bar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        undo_btn = Gtk.Button(label="↩ Desfazer")
        undo_btn.set_tooltip_text("Ctrl+Z")
        undo_btn.connect("clicked", lambda _: self._undo())
        bar.append(undo_btn)

        bar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        copy_btn = Gtk.Button(label="📋 Copiar")
        copy_btn.set_tooltip_text("Ctrl+C")
        copy_btn.connect("clicked", lambda _: self._do_copy())
        bar.append(copy_btn)

        save_btn = Gtk.Button(label="💾 Salvar")
        save_btn.set_tooltip_text("Ctrl+S")
        save_btn.connect("clicked", lambda _: self._do_save())
        bar.append(save_btn)

        bar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        exit_btn = Gtk.Button(label="✕ Sair")
        exit_btn.set_tooltip_text("Esc")
        exit_btn.connect("clicked", lambda _: self.close())
        bar.append(exit_btn)

        self._toolbar = bar
        self._root.add_overlay(bar)

    def _wire_input(self):
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin",  self._drag_begin)
        drag.connect("drag-update", self._drag_update)
        drag.connect("drag-end",    self._drag_end)
        self._drawing.add_controller(drag)

    def _wire_keyboard(self):
        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._key_pressed)
        self.add_controller(key)

    # ------------------------------------------------------------------
    # Ponto de entrada chamado por main.py
    # ------------------------------------------------------------------

    def start_annotation(self, x: int, y: int, w: int, h: int):
        """Abre a janela maximizada mostrando a região (x,y,w,h) do screenshot."""
        self._roi = (x, y, w, h)
        self.maximize()
        self._drawing.queue_draw()

    # ------------------------------------------------------------------
    # Transformação janela ↔ imagem (ROI escalado para preencher a janela)
    # ------------------------------------------------------------------

    def _update_transform(self, win_w, win_h):
        if self._roi is None:
            return
        roi_x, roi_y, roi_w, roi_h = self._roi
        self._scale    = min(win_w / roi_w, win_h / roi_h)
        self._offset_x = (win_w - roi_w * self._scale) / 2
        self._offset_y = (win_h - roi_h * self._scale) / 2
        self._roi_x    = roi_x
        self._roi_y    = roi_y

    def _win_to_img(self, wx, wy):
        """Converte coordenada de janela → coordenada de imagem original."""
        ix = (wx - self._offset_x) / self._scale + self._roi_x
        iy = (wy - self._offset_y) / self._scale + self._roi_y
        return ix, iy

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------

    def _on_draw(self, _area, cr, width, height):
        if self._roi is None:
            return

        self._update_transform(width, height)
        roi_x, roi_y, roi_w, roi_h = self._roi

        # Screenshot: recorta o ROI e escala para a janela
        cr.save()
        cr.translate(self._offset_x, self._offset_y)
        cr.scale(self._scale, self._scale)
        # translate para que o pixel roi_x,roi_y apareça em (0,0)
        Gdk.cairo_set_source_pixbuf(cr, self._screenshot, -roi_x, -roi_y)
        cr.paint()
        cr.restore()

        # Shapes em coordenadas de imagem → aplicar o mesmo transform
        cr.save()
        cr.translate(self._offset_x, self._offset_y)
        cr.scale(self._scale, self._scale)
        cr.translate(-roi_x, -roi_y)
        for shape in self._shapes:
            shape.draw(cr)
        if self._active_shape:
            self._active_shape.draw(cr)
        cr.restore()

    # ------------------------------------------------------------------
    # Input: drag para desenhar
    # ------------------------------------------------------------------

    def _drag_begin(self, gesture, sx, sy):
        ix, iy = self._win_to_img(sx, sy)
        color = COLORS[self._current_color_idx]
        self._push_undo()
        if self._current_tool == "text":
            self._active_shape = TextAnnotation(ix, iy, color=color, width=self._stroke_width)
        else:
            self._active_shape = make_shape(self._current_tool, ix, iy, color, self._stroke_width)
        self._drawing.queue_draw()

    def _drag_update(self, gesture, ddx, ddy):
        _, sx0, sy0 = gesture.get_start_point()
        ix, iy = self._win_to_img(sx0 + ddx, sy0 + ddy)
        if self._active_shape:
            self._active_shape.update(ix, iy)
        self._drawing.queue_draw()

    def _drag_end(self, _gesture, _ddx, _ddy):
        if self._active_shape and self._current_tool != "text":
            self._shapes.append(self._active_shape)
            self._active_shape = None
        self._drawing.queue_draw()

    # ------------------------------------------------------------------
    # Teclado
    # ------------------------------------------------------------------

    def _key_pressed(self, _ctrl, keyval, _keycode, state):
        ctrl_mask = bool(state & Gdk.ModifierType.CONTROL_MASK)

        if keyval == Gdk.KEY_Escape:
            self.close()
            return True

        if ctrl_mask:
            if keyval == Gdk.KEY_z: self._undo();    return True
            if keyval == Gdk.KEY_c: self._do_copy(); return True
            if keyval == Gdk.KEY_s: self._do_save(); return True

        mapping = {Gdk.KEY_r: "rect", Gdk.KEY_l: "line",
                   Gdk.KEY_a: "arrow", Gdk.KEY_t: "text"}
        if keyval in mapping:
            self._set_tool(mapping[keyval])
            return True

        if keyval == Gdk.KEY_c:
            self._cycle_color()
            return True

        if self._current_tool == "text" and self._active_shape:
            if keyval == Gdk.KEY_BackSpace:
                self._active_shape.text = self._active_shape.text[:-1]
            elif keyval == Gdk.KEY_Return:
                self._shapes.append(self._active_shape)
                self._active_shape = None
            else:
                ch = chr(keyval) if 32 <= keyval <= 126 else ""
                if ch:
                    self._active_shape.text += ch
            self._drawing.queue_draw()
            return True

        return False

    # ------------------------------------------------------------------
    # Ferramentas / cores
    # ------------------------------------------------------------------

    def _set_tool(self, tool):
        self._current_tool = tool
        self._refresh_tool_buttons()

    def _refresh_tool_buttons(self):
        for t, btn in self._tool_buttons.items():
            if t == self._current_tool:
                btn.add_css_class("tool-active")
            else:
                btn.remove_css_class("tool-active")

    def _on_tool_click(self, _btn, tool):
        self._set_tool(tool)

    def _set_width(self, w):
        self._stroke_width = w

    def _cycle_color(self):
        self._current_color_idx = (self._current_color_idx + 1) % len(COLORS)
        r, g, b, _ = COLORS[self._current_color_idx]
        hex_c = "#{:02x}{:02x}{:02x}".format(int(r*255), int(g*255), int(b*255))
        self._color_label.set_markup(
            f'<span color="{hex_c}">●</span> {COLOR_NAMES[self._current_color_idx]}'
        )

    # ------------------------------------------------------------------
    # Undo
    # ------------------------------------------------------------------

    def _push_undo(self):
        import copy
        self._undo_history.append([copy.copy(s) for s in self._shapes])

    def _undo(self):
        if self._undo_history:
            self._shapes = self._undo_history.pop()
            self._active_shape = None
            self._drawing.queue_draw()

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _render_to_surface(self):
        """Renderiza o ROI com shapes em ImageSurface."""
        if not self._roi:
            return None
        roi_x, roi_y, roi_w, roi_h = self._roi
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, roi_w, roi_h)
        cr = cairo.Context(surface)
        # Recorta o screenshot na região de interesse
        cr.translate(-roi_x, -roi_y)
        Gdk.cairo_set_source_pixbuf(cr, self._screenshot, 0, 0)
        cr.paint()
        # Shapes em coordenadas absolutas — o translate já compensa
        for shape in self._shapes:
            shape.draw(cr)
        return surface

    def _do_copy(self):
        surface = self._render_to_surface()
        if surface and self._roi:
            # Para o exporter, a sel é (0,0,w,h) porque já recortamos
            roi_w, roi_h = self._roi[2], self._roi[3]
            ok = self._exporter.copy_surface_to_clipboard(surface, (0, 0, roi_w, roi_h))
            if ok:
                self._show_toast("✓ Copiado para o clipboard!")

    def _do_save(self):
        surface = self._render_to_surface()
        if surface and self._roi:
            roi_w, roi_h = self._roi[2], self._roi[3]
            self._exporter.save_surface_to_file(
                surface, (0, 0, roi_w, roi_h),
                on_done=self._on_saved,
            )

    def _on_saved(self, path):
        if path:
            print(f"[fallenshot] Salvo: {path}")
            self.close()
        # Se cancelou o diálogo, não faz nada — app continua aberto

    # ------------------------------------------------------------------
    # Toast
    # ------------------------------------------------------------------

    def _show_toast(self, message: str):
        print(f"[fallenshot] {message}")
        label = Gtk.Label(label=message)
        label.add_css_class("toolbar-box")
        label.set_halign(Gtk.Align.CENTER)
        label.set_valign(Gtk.Align.START)
        label.set_margin_top(20)
        self._root.add_overlay(label)
        GLib.timeout_add(2500, lambda: (self._root.remove_overlay(label), False)[1])
