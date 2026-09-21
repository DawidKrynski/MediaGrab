import ctypes
from pathlib import Path
from types import SimpleNamespace

from mediagrab import reveal


def test_windows_reveal_uses_shell_without_dbus(tmp_path, monkeypatch):
    first, second = tmp_path / "example image.jpg", tmp_path / "example-video.mp4"
    first.touch()
    second.touch()
    selected, folders = [], []
    monkeypatch.setattr(reveal.sys, "platform", "win32")
    monkeypatch.setattr(reveal, "select_in_explorer", lambda paths: selected.append(paths) or True)
    monkeypatch.setattr(reveal, "reveal_message", lambda _: (_ for _ in ()).throw(AssertionError()))
    result = reveal.reveal_files([first, second, first], opener=folders.append)
    assert result.selected
    assert selected == [[first, second]] and not folders


def test_windows_failed_selection_falls_back_once_per_folder(tmp_path, monkeypatch):
    files = [tmp_path / "a.jpg", tmp_path / "b.jpg"]
    for file in files:
        file.touch()
    folders = []
    monkeypatch.setattr(reveal.sys, "platform", "win32")
    monkeypatch.setattr(reveal, "select_in_explorer", lambda _: False)
    result = reveal.reveal_files(files, opener=folders.append)
    assert not result.selected and "containing folder" in result.message
    assert folders == [tmp_path]


def test_windows_open_folder_uses_default_shell_handler(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(reveal.sys, "platform", "win32")
    monkeypatch.setattr(reveal.os, "startfile", opened.append, raising=False)
    reveal.open_directory(tmp_path)
    assert opened == [str(tmp_path)]


class NativeFunction:
    def __init__(self, implementation):
        self.implementation = implementation

    def __call__(self, *args):
        return self.implementation(*args)


def fake_windows_shell(monkeypatch, *, parse_failure=None, selection_failure=False):
    parsed, freed, selected, uninitialized = [], [], [], []

    def parse(name, context, pointer, flags, attributes):
        if name == parse_failure:
            return -1
        parsed.append(name)
        ctypes.cast(pointer, ctypes.POINTER(ctypes.c_void_p))[0] = len(parsed)
        return 0

    def select(parent, count, items, flags):
        selected.append((parent.value, list(items[:count])))
        return -1 if selection_failure else 0

    shell = SimpleNamespace(
        SHParseDisplayName=NativeFunction(parse),
        ILFindLastID=NativeFunction(lambda p: p.value + 100),
        SHOpenFolderAndSelectItems=NativeFunction(select),
    )
    ole = SimpleNamespace(
        CoInitializeEx=NativeFunction(lambda *_: 0),
        CoUninitialize=NativeFunction(lambda: uninitialized.append(True)),
        CoTaskMemFree=NativeFunction(lambda p: freed.append(p.value)),
    )
    monkeypatch.setattr(
        ctypes, "WinDLL", lambda name, **_: shell if name == "shell32" else ole, raising=False
    )
    return parsed, freed, selected, uninitialized


def test_windows_shell_groups_folders_and_releases_every_pidl(tmp_path, monkeypatch):
    paths = [tmp_path / "one" / "a.jpg", tmp_path / "one" / "b.jpg", tmp_path / "two" / "c.jpg"]
    parsed, freed, selected, uninitialized = fake_windows_shell(monkeypatch)
    assert reveal.select_in_explorer(paths)
    assert parsed == [
        str(paths[0].parent),
        str(paths[0]),
        str(paths[1]),
        str(paths[2].parent),
        str(paths[2]),
    ]
    assert selected == [(1, [102, 103]), (4, [105])]
    assert freed == [3, 2, 1, 5, 4] and uninitialized == [True]


def test_windows_shell_failure_releases_memory_and_com(tmp_path, monkeypatch):
    path = tmp_path / "file.jpg"
    _, freed, _, uninitialized = fake_windows_shell(monkeypatch, selection_failure=True)
    assert not reveal.select_in_explorer([path])
    assert freed == [2, 1] and uninitialized == [True]


def test_empty_reveal_never_opens_explorer(tmp_path, monkeypatch):
    monkeypatch.setattr(reveal.sys, "platform", "win32")
    monkeypatch.setattr(
        reveal, "select_in_explorer", lambda _: (_ for _ in ()).throw(AssertionError())
    )
    assert not reveal.reveal_files([Path(tmp_path / "absent")]).selected
