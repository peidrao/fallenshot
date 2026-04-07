from __future__ import annotations

from src import drawing


class FakeContext:
    def __init__(self):
        self.calls = []

    def _record(self, name, *args):
        self.calls.append((name, args))

    def set_source_rgba(self, *args):
        self._record("set_source_rgba", *args)

    def set_line_width(self, *args):
        self._record("set_line_width", *args)

    def set_line_cap(self, *args):
        self._record("set_line_cap", *args)

    def set_line_join(self, *args):
        self._record("set_line_join", *args)

    def rectangle(self, *args):
        self._record("rectangle", *args)

    def stroke(self):
        self._record("stroke")

    def move_to(self, *args):
        self._record("move_to", *args)

    def line_to(self, *args):
        self._record("line_to", *args)

    def select_font_face(self, *args):
        self._record("select_font_face", *args)

    def set_font_size(self, *args):
        self._record("set_font_size", *args)

    def show_text(self, *args):
        self._record("show_text", *args)


def test_make_shape_known_and_unknown_tools():
    style = ((1, 0, 0, 1), 2.0)
    assert isinstance(drawing.make_shape("rect", 1, 2, *style), drawing.Rectangle)
    assert isinstance(drawing.make_shape("line", 1, 2, *style), drawing.Line)
    assert isinstance(drawing.make_shape("arrow", 1, 2, *style), drawing.Arrow)
    assert isinstance(drawing.make_shape("text", 1, 2, *style), drawing.TextAnnotation)
    assert drawing.make_shape("unknown", 1, 2, *style) is None


def test_rectangle_draw_skips_tiny_shapes_and_draws_valid():
    rect = drawing.Rectangle(10, 10, color=(1, 1, 1, 1), width=2)
    rect.update(10.4, 10.3)
    ctx = FakeContext()
    rect.draw(ctx)
    assert ctx.calls == []

    rect.update(20, 30)
    rect.draw(ctx)
    names = [c[0] for c in ctx.calls]
    assert "rectangle" in names
    assert "stroke" in names


def test_arrow_draw_short_segment_is_ignored():
    arrow = drawing.Arrow(0, 0, color=(1, 0, 0, 1), width=3)
    arrow.update(1, 1)
    ctx = FakeContext()
    arrow.draw(ctx)
    assert ctx.calls == []


def test_text_annotation_draw_and_update_behaviour():
    text = drawing.TextAnnotation(5, 6, color=(0, 1, 0, 1), width=2)
    ctx = FakeContext()
    text.draw(ctx)
    assert ctx.calls == []

    text.text = "abc"
    text.update(99, 100)
    text.draw(ctx)
    names = [c[0] for c in ctx.calls]
    assert names.count("show_text") == 2
