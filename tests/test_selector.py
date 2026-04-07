from __future__ import annotations

from src.selector import SelectorWindow


class DummyArea:
    def __init__(self):
        self.queued = 0

    def queue_draw(self):
        self.queued += 1


def _make_selector():
    selector = SelectorWindow.__new__(SelectorWindow)
    selector._img_w = 200
    selector._img_h = 100
    selector._scale = 1.0
    selector._off_x = 0.0
    selector._off_y = 0.0
    selector._sel_start = None
    selector._sel_end = None
    selector._area = DummyArea()
    selector._pixbuf = object()
    selector._closed = False
    selector.close = lambda: setattr(selector, "_closed", True)
    return selector


def test_transform_and_coordinate_conversion():
    selector = _make_selector()

    selector._update_transform(300, 300)
    assert selector._scale == 1.5
    assert selector._off_x == 0
    assert selector._off_y == 75

    img = selector._win_to_img(150, 150)
    assert img == (100.0, 50.0)


def test_sel_rect_win_returns_normalized_rect():
    selector = _make_selector()
    selector._sel_start = (50, 30)
    selector._sel_end = (10, 20)

    assert selector._sel_rect_win() == (10, 20, 40, 10)


def test_drag_end_clears_small_selection():
    selector = _make_selector()
    selector._sel_start = (0, 0)
    selector._sel_end = (5, 8)

    selector._drag_end(object(), 0, 0)

    assert selector._sel_start is None
    assert selector._sel_end is None
    assert selector._area.queued == 1


def test_confirm_clamps_and_invokes_callback():
    selector = _make_selector()
    selector._scale = 1.0
    selector._off_x = 0.0
    selector._off_y = 0.0
    selector._sel_start = (-10, -5)
    selector._sel_end = (999, 999)

    selected = []
    selector._on_selected = lambda pixbuf, x, y, w, h: selected.append((pixbuf, x, y, w, h))

    selector._confirm()

    assert selector._closed is True
    assert selected[0][1:] == (0, 0, 200, 100)


def test_on_key_escape_closes_and_calls_cancelled():
    selector = _make_selector()
    cancelled = []
    selector._on_cancelled = lambda: cancelled.append(True)

    handled = selector._on_key(object(), 27, 0, 0)

    assert handled is True
    assert selector._closed is True
    assert cancelled == [True]
