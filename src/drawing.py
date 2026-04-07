"""
drawing.py — Formas anotáveis usando Cairo.

Cada shape tem um método draw(cr) e from_drag(x1,y1,x2,y2).
"""

import cairo
import math


class Shape:
    def __init__(self, color=(1.0, 0.2, 0.2, 1.0), width=2.5):
        self.color = color
        self.width = width

    def _apply_style(self, cr):
        cr.set_source_rgba(*self.color)
        cr.set_line_width(self.width)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)

    def draw(self, cr):
        raise NotImplementedError

    def update(self, x, y):
        raise NotImplementedError


class Rectangle(Shape):
    def __init__(self, x1, y1, x2=None, y2=None, **kw):
        super().__init__(**kw)
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2 if x2 is not None else x1
        self.y2 = y2 if y2 is not None else y1

    def update(self, x, y):
        self.x2 = x
        self.y2 = y

    def draw(self, cr):
        x = min(self.x1, self.x2)
        y = min(self.y1, self.y2)
        w = abs(self.x2 - self.x1)
        h = abs(self.y2 - self.y1)
        if w < 1 or h < 1:
            return
        self._apply_style(cr)
        cr.rectangle(x, y, w, h)
        cr.stroke()


class Line(Shape):
    def __init__(self, x1, y1, x2=None, y2=None, **kw):
        super().__init__(**kw)
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2 if x2 is not None else x1
        self.y2 = y2 if y2 is not None else y1

    def update(self, x, y):
        self.x2 = x
        self.y2 = y

    def draw(self, cr):
        self._apply_style(cr)
        cr.move_to(self.x1, self.y1)
        cr.line_to(self.x2, self.y2)
        cr.stroke()


class Arrow(Shape):
    ARROW_HEAD = 16  # pixels

    def __init__(self, x1, y1, x2=None, y2=None, **kw):
        super().__init__(**kw)
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2 if x2 is not None else x1
        self.y2 = y2 if y2 is not None else y1

    def update(self, x, y):
        self.x2 = x
        self.y2 = y

    def draw(self, cr):
        dx = self.x2 - self.x1
        dy = self.y2 - self.y1
        length = math.hypot(dx, dy)
        if length < 4:
            return

        self._apply_style(cr)

        # Linha principal
        cr.move_to(self.x1, self.y1)
        cr.line_to(self.x2, self.y2)
        cr.stroke()

        # Ponta da seta
        angle = math.atan2(dy, dx)
        a = self.ARROW_HEAD
        for side in (+0.4, -0.4):
            ax = self.x2 - a * math.cos(angle - side)
            ay = self.y2 - a * math.sin(angle - side)
            cr.move_to(self.x2, self.y2)
            cr.line_to(ax, ay)
        cr.stroke()


class TextAnnotation(Shape):
    def __init__(self, x, y, text="", font_size=18, **kw):
        super().__init__(**kw)
        self.x = x
        self.y = y
        self.text = text
        self.font_size = font_size

    def update(self, x, y):
        pass  # texto não é arrastado

    def draw(self, cr):
        if not self.text:
            return
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(self.font_size)

        # Sombra
        cr.set_source_rgba(0, 0, 0, 0.6)
        cr.move_to(self.x + 1, self.y + 1)
        cr.show_text(self.text)

        # Texto
        self._apply_style(cr)
        cr.move_to(self.x, self.y)
        cr.show_text(self.text)


def make_shape(tool, x, y, color, width):
    """Factory: cria a shape correta para o tool ativo."""
    kw = dict(color=color, width=width)
    if tool == "rect":
        return Rectangle(x, y, **kw)
    elif tool == "line":
        return Line(x, y, **kw)
    elif tool == "arrow":
        return Arrow(x, y, **kw)
    elif tool == "text":
        return TextAnnotation(x, y, **kw)
    return None
