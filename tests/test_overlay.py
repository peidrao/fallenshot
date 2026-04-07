from __future__ import annotations

from src.overlay import OverlayWindow, TextAnnotation


class DummyArea:
    def __init__(self):
        self.queued = 0

    def queue_draw(self):
        self.queued += 1


class DummyExport:
    def __init__(self):
        self.copy_calls = []
        self.save_calls = []

    def copy_surface_to_clipboard(self, surface, selection):
        self.copy_calls.append((surface, selection))
        return True

    def save_surface_to_file(self, surface, selection, on_done):
        self.save_calls.append((surface, selection))
        on_done("/tmp/file.png")


def _make_overlay():
    overlay = OverlayWindow.__new__(OverlayWindow)
    overlay._image_width = 300
    overlay._image_height = 200
    overlay._region_of_interest = None
    overlay._drawing_area = DummyArea()
    overlay._active_tool = "rect"
    overlay._active_color_index = 0
    overlay._stroke_width = 2.5
    overlay._shapes = []
    overlay._undo_history = []
    overlay._active_shape = None
    overlay._show_toast_calls = []
    overlay._show_toast = lambda msg: overlay._show_toast_calls.append(msg)
    overlay._render_to_surface = lambda: object()
    overlay._export_manager = DummyExport()
    overlay._closed = False
    overlay.maximize = lambda: setattr(overlay, "_maximized", True)
    overlay.close = lambda: setattr(overlay, "_closed", True)
    overlay._tool_buttons = {}
    overlay._refresh_tool_buttons = lambda: None
    return overlay


def test_start_annotation_validates_and_updates_state():
    overlay = _make_overlay()

    overlay.start_annotation(10, 20, 100, 50)
    assert overlay._region_of_interest == (10, 20, 100, 50)
    assert overlay._drawing_area.queued == 1


def test_start_annotation_rejects_invalid_region():
    overlay = _make_overlay()

    try:
        overlay.start_annotation(300, 200, 50, 50)
        assert False, "expected ValueError"
    except ValueError:
        assert True


def test_handle_text_input_backspace_enter_and_append():
    overlay = _make_overlay()
    overlay._active_tool = "text"
    overlay._active_shape = TextAnnotation(0, 0, text="ab", color=(1, 1, 1, 1), width=2)

    assert overlay._handle_text_input(65288) is True  # backspace
    assert overlay._active_shape.text == "a"

    assert overlay._handle_text_input(ord("x")) is True
    assert overlay._active_shape.text == "ax"

    assert overlay._handle_text_input(65293) is True  # enter
    assert len(overlay._shapes) == 1
    assert overlay._active_shape is None


def test_handle_text_input_non_printable_returns_false():
    overlay = _make_overlay()
    overlay._active_tool = "text"
    overlay._active_shape = TextAnnotation(0, 0, text="ab", color=(1, 1, 1, 1), width=2)
    assert overlay._handle_text_input(10) is False
    assert overlay._active_shape.text == "ab"


def test_undo_restores_previous_shapes():
    overlay = _make_overlay()
    overlay._shapes = ["new"]
    overlay._undo_history = [["old"]]
    overlay._active_shape = "temp"

    overlay._undo()

    assert overlay._shapes == ["old"]
    assert overlay._active_shape is None
    assert overlay._drawing_area.queued == 1


def test_copy_and_save_selection_flow():
    overlay = _make_overlay()
    overlay._region_of_interest = (0, 0, 40, 20)

    overlay._copy_selection()
    assert overlay._export_manager.copy_calls
    assert overlay._show_toast_calls == ["Copied to clipboard."]

    overlay._save_selection()
    assert overlay._export_manager.save_calls
    assert overlay._closed is True


def test_copy_and_save_selection_noop_without_region():
    overlay = _make_overlay()
    overlay._region_of_interest = None
    overlay._copy_selection()
    overlay._save_selection()
    assert overlay._export_manager.copy_calls == []
    assert overlay._export_manager.save_calls == []


def test_render_to_surface_returns_none_without_roi():
    overlay = _make_overlay()
    overlay._region_of_interest = None
    overlay._render_to_surface = OverlayWindow._render_to_surface.__get__(overlay, OverlayWindow)
    assert overlay._render_to_surface() is None


def test_on_key_pressed_shortcuts(monkeypatch):
    overlay = _make_overlay()

    calls = []
    overlay._undo = lambda: calls.append("undo")
    overlay._copy_selection = lambda: calls.append("copy")
    overlay._save_selection = lambda: calls.append("save")
    overlay._set_tool = lambda tool: calls.append(("tool", tool))
    overlay._cycle_color = lambda: calls.append("cycle")

    assert overlay._on_key_pressed(object(), 122, 0, 0x4) is True
    assert overlay._on_key_pressed(object(), 99, 0, 0x4) is True
    assert overlay._on_key_pressed(object(), 115, 0, 0x4) is True
    assert overlay._on_key_pressed(object(), 114, 0, 0) is True
    assert overlay._on_key_pressed(object(), 99, 0, 0) is True

    assert calls == ["undo", "copy", "save", ("tool", "rect"), "cycle"]
