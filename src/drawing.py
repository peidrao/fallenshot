"""Drawing primitives used by the annotation overlay."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod

import cairo


class Shape(ABC):
    """Base contract for drawable annotations."""

    def __init__(self, color: tuple[float, float, float, float], width: float) -> None:
        self.color = color
        self.width = width

    def _apply_style(self, context: cairo.Context) -> None:
        """Apply stroke style shared by all shape types."""
        context.set_source_rgba(*self.color)
        context.set_line_width(self.width)
        context.set_line_cap(cairo.LINE_CAP_ROUND)
        context.set_line_join(cairo.LINE_JOIN_ROUND)

    @abstractmethod
    def draw(self, context: cairo.Context) -> None:
        """Draw the shape into the provided Cairo context."""

    @abstractmethod
    def update(self, x: float, y: float) -> None:
        """Update shape geometry from pointer interaction."""


class Rectangle(Shape):
    """Axis-aligned rectangle defined by two corner points."""

    def __init__(
        self,
        x1: float,
        y1: float,
        x2: float | None = None,
        y2: float | None = None,
        **style: object,
    ) -> None:
        super().__init__(**style)
        self.x1 = x1
        self.y1 = y1
        self.x2 = x1 if x2 is None else x2
        self.y2 = y1 if y2 is None else y2

    def update(self, x: float, y: float) -> None:
        self.x2 = x
        self.y2 = y

    def draw(self, context: cairo.Context) -> None:
        x = min(self.x1, self.x2)
        y = min(self.y1, self.y2)
        width = abs(self.x2 - self.x1)
        height = abs(self.y2 - self.y1)

        if width < 1 or height < 1:
            return

        self._apply_style(context)
        context.rectangle(x, y, width, height)
        context.stroke()


class Line(Shape):
    """Straight line segment between two points."""

    def __init__(
        self,
        x1: float,
        y1: float,
        x2: float | None = None,
        y2: float | None = None,
        **style: object,
    ) -> None:
        super().__init__(**style)
        self.x1 = x1
        self.y1 = y1
        self.x2 = x1 if x2 is None else x2
        self.y2 = y1 if y2 is None else y2

    def update(self, x: float, y: float) -> None:
        self.x2 = x
        self.y2 = y

    def draw(self, context: cairo.Context) -> None:
        self._apply_style(context)
        context.move_to(self.x1, self.y1)
        context.line_to(self.x2, self.y2)
        context.stroke()


class Arrow(Shape):
    """Line segment with an arrow head at the end point."""

    ARROW_HEAD_LENGTH = 16
    ARROW_HEAD_ANGLE = 0.4

    def __init__(
        self,
        x1: float,
        y1: float,
        x2: float | None = None,
        y2: float | None = None,
        **style: object,
    ) -> None:
        super().__init__(**style)
        self.x1 = x1
        self.y1 = y1
        self.x2 = x1 if x2 is None else x2
        self.y2 = y1 if y2 is None else y2

    def update(self, x: float, y: float) -> None:
        self.x2 = x
        self.y2 = y

    def draw(self, context: cairo.Context) -> None:
        delta_x = self.x2 - self.x1
        delta_y = self.y2 - self.y1
        length = math.hypot(delta_x, delta_y)
        if length < 4:
            return

        self._apply_style(context)
        context.move_to(self.x1, self.y1)
        context.line_to(self.x2, self.y2)
        context.stroke()

        angle = math.atan2(delta_y, delta_x)
        for side in (self.ARROW_HEAD_ANGLE, -self.ARROW_HEAD_ANGLE):
            tip_x = self.x2 - self.ARROW_HEAD_LENGTH * math.cos(angle - side)
            tip_y = self.y2 - self.ARROW_HEAD_LENGTH * math.sin(angle - side)
            context.move_to(self.x2, self.y2)
            context.line_to(tip_x, tip_y)
        context.stroke()


class TextAnnotation(Shape):
    """Text label anchored at a fixed image position."""

    def __init__(
        self,
        x: float,
        y: float,
        text: str = "",
        font_size: int = 18,
        **style: object,
    ) -> None:
        super().__init__(**style)
        self.x = x
        self.y = y
        self.text = text
        self.font_size = font_size

    def update(self, x: float, y: float) -> None:
        """Text annotations keep their anchor point after creation."""
        return

    def draw(self, context: cairo.Context) -> None:
        if not self.text:
            return

        context.select_font_face(
            "Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD
        )
        context.set_font_size(self.font_size)

        context.set_source_rgba(0, 0, 0, 0.6)
        context.move_to(self.x + 1, self.y + 1)
        context.show_text(self.text)

        self._apply_style(context)
        context.move_to(self.x, self.y)
        context.show_text(self.text)


def make_shape(
    tool: str,
    x: float,
    y: float,
    color: tuple[float, float, float, float],
    width: float,
) -> Shape | None:
    """Instantiate a shape for the selected drawing tool."""
    style = {"color": color, "width": width}
    shape_factories = {
        "rect": Rectangle,
        "line": Line,
        "arrow": Arrow,
        "text": TextAnnotation,
    }
    shape_type = shape_factories.get(tool)
    if shape_type is None:
        return None
    return shape_type(x, y, **style)
