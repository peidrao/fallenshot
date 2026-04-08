from __future__ import annotations

from src.export import ExportManager


class FakePixbuf:
    def __init__(self, width=100, height=80):
        self._w = width
        self._h = height
        self.saved = []

    def get_width(self):
        return self._w

    def get_height(self):
        return self._h

    def new_subpixbuf(self, x, y, w, h):
        return (x, y, w, h)

    def savev(self, path, _fmt, _a, _b):
        self.saved.append(path)
        with open(path, "wb") as f:
            f.write(b"png")


def test_crop_surface_applies_bounds(monkeypatch):
    monkeypatch.setattr(
        ExportManager, "_surface_to_pixbuf", staticmethod(lambda _s: FakePixbuf(40, 30))
    )

    sub = ExportManager._crop_surface(object(), (10, 5, 100, 100))
    assert sub == (10, 5, 30, 25)


def test_copy_surface_to_clipboard_without_wlcopy_returns_false(monkeypatch):
    manager = ExportManager(parent_window=object())
    monkeypatch.setattr("src.export.shutil.which", lambda _cmd: None)
    assert manager.copy_surface_to_clipboard(object(), (0, 0, 10, 10)) is False


def test_copy_surface_to_clipboard_success(monkeypatch, tmp_path):
    manager = ExportManager(parent_window=object())
    cropped = FakePixbuf()

    monkeypatch.setattr("src.export.shutil.which", lambda _cmd: "/usr/bin/wl-copy")
    monkeypatch.setattr(manager, "_crop_surface", lambda _surface, _sel: cropped)

    temp_file = tmp_path / "capture.png"

    class FakeTemp:
        def __init__(self, name):
            self.name = str(name)

        def close(self):
            return None

    run_calls = []

    monkeypatch.setattr(
        "src.export.tempfile.NamedTemporaryFile",
        lambda suffix, delete: FakeTemp(temp_file),
    )
    monkeypatch.setattr("src.export.subprocess.run", lambda *a, **k: run_calls.append((a, k)))
    monkeypatch.setattr("src.export.os.unlink", lambda p: None)

    ok = manager.copy_surface_to_clipboard(object(), (0, 0, 20, 20))

    assert ok is True
    assert cropped.saved
    assert run_calls


def test_copy_surface_to_clipboard_returns_false_when_crop_fails(monkeypatch):
    manager = ExportManager(parent_window=object())
    monkeypatch.setattr("src.export.shutil.which", lambda _cmd: "/usr/bin/wl-copy")
    monkeypatch.setattr(manager, "_crop_surface", lambda _surface, _sel: None)

    assert manager.copy_surface_to_clipboard(object(), (0, 0, 10, 10)) is False


def test_save_surface_to_file_cancel_calls_callback(monkeypatch):
    manager = ExportManager(parent_window=object())

    stored = {}

    class FakeDialog:
        def add_button(self, *_args):
            return None

        def set_current_name(self, _name):
            return None

        def set_current_folder(self, _folder):
            return None

        def add_filter(self, _filter):
            return None

        def connect(self, _name, cb):
            stored["cb"] = cb
            return 1

        def present(self):
            return None

        def destroy(self):
            return None

        def get_file(self):
            return None

    monkeypatch.setattr("src.export.Gtk.FileChooserDialog", lambda **kwargs: FakeDialog())
    monkeypatch.setattr("src.export.Gio.File.new_for_path", lambda path: path)

    outputs = []
    manager.save_surface_to_file(object(), (0, 0, 10, 10), on_done=outputs.append)

    stored["cb"](FakeDialog(), 0)
    assert outputs == [None]


def test_save_surface_to_file_accept_adds_png_extension(monkeypatch, tmp_path):
    manager = ExportManager(parent_window=object())

    class SelectedFile:
        def __init__(self, path):
            self._path = path

        def get_path(self):
            return self._path

    stored = {}

    class FakeDialog:
        def __init__(self):
            self._file = SelectedFile(str(tmp_path / "shot"))

        def add_button(self, *_args):
            return None

        def set_current_name(self, _name):
            return None

        def set_current_folder(self, _folder):
            return None

        def add_filter(self, _filter):
            return None

        def connect(self, _name, cb):
            stored["cb"] = cb
            stored["dlg"] = self
            return 1

        def present(self):
            return None

        def destroy(self):
            return None

        def get_file(self):
            return self._file

    saved_paths = []

    class Crop(FakePixbuf):
        def savev(self, path, _fmt, _a, _b):
            saved_paths.append(path)

    monkeypatch.setattr("src.export.Gtk.FileChooserDialog", lambda **kwargs: FakeDialog())
    monkeypatch.setattr("src.export.Gio.File.new_for_path", lambda path: path)
    monkeypatch.setattr(manager, "_crop_surface", lambda _surface, _sel: Crop())

    outputs = []
    manager.save_surface_to_file(object(), (0, 0, 10, 10), on_done=outputs.append)

    stored["cb"](stored["dlg"], 1)
    assert saved_paths[0].endswith(".png")
    assert outputs[0].endswith(".png")


def test_save_surface_to_file_accept_with_empty_path_calls_none(monkeypatch):
    manager = ExportManager(parent_window=object())

    class SelectedFile:
        def get_path(self):
            return ""

    stored = {}

    class FakeDialog:
        def __init__(self):
            self._file = SelectedFile()

        def add_button(self, *_args):
            return None

        def set_current_name(self, _name):
            return None

        def set_current_folder(self, _folder):
            return None

        def add_filter(self, _filter):
            return None

        def connect(self, _name, cb):
            stored["cb"] = cb
            stored["dlg"] = self
            return 1

        def present(self):
            return None

        def destroy(self):
            return None

        def get_file(self):
            return self._file

    monkeypatch.setattr("src.export.Gtk.FileChooserDialog", lambda **kwargs: FakeDialog())
    monkeypatch.setattr("src.export.Gio.File.new_for_path", lambda path: path)

    outputs = []
    manager.save_surface_to_file(object(), (0, 0, 10, 10), on_done=outputs.append)
    stored["cb"](stored["dlg"], 1)
    assert outputs == [None]


def test_save_surface_to_file_accept_save_error_calls_none(monkeypatch, tmp_path):
    manager = ExportManager(parent_window=object())

    class SelectedFile:
        def __init__(self, path):
            self._path = path

        def get_path(self):
            return self._path

    stored = {}

    class FakeDialog:
        def __init__(self):
            self._file = SelectedFile(str(tmp_path / "shot"))

        def add_button(self, *_args):
            return None

        def set_current_name(self, _name):
            return None

        def set_current_folder(self, _folder):
            return None

        def add_filter(self, _filter):
            return None

        def connect(self, _name, cb):
            stored["cb"] = cb
            stored["dlg"] = self
            return 1

        def present(self):
            return None

        def destroy(self):
            return None

        def get_file(self):
            return self._file

    class BrokenCrop(FakePixbuf):
        def savev(self, _path, _fmt, _a, _b):
            raise RuntimeError("disk full")

    monkeypatch.setattr("src.export.Gtk.FileChooserDialog", lambda **kwargs: FakeDialog())
    monkeypatch.setattr("src.export.Gio.File.new_for_path", lambda path: path)
    monkeypatch.setattr(manager, "_crop_surface", lambda _surface, _sel: BrokenCrop())

    outputs = []
    manager.save_surface_to_file(object(), (0, 0, 10, 10), on_done=outputs.append)
    stored["cb"](stored["dlg"], 1)
    assert outputs == [None]


def test_surface_to_pixbuf_handles_write_failures(monkeypatch):
    class BrokenSurface:
        def write_to_png(self, _buffer):
            raise RuntimeError("boom")

    assert ExportManager._surface_to_pixbuf(BrokenSurface()) is None
