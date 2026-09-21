import time
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication

from mediagrab.models import BatchResult, CollectionRequired, Inspection, MediaError, MediaItem
from mediagrab.quick import QuickWindow, clipboard_url
from mediagrab.reveal import RevealResult
from mediagrab.service import MediaService


def media(key="one", *, collection=False, kind="image"):
    return MediaItem(
        key,
        "gallery",
        "instagram",
        key,
        "Media " + key,
        kind,
        "https://instagram.com/p/post/",
        thumbnail="https://invalid.test/thumb.jpg",
        collection=collection,
    )


@pytest.fixture
def quick(qtbot, tmp_path):
    events = []
    settings = QSettings(str(tmp_path / "prefs.ini"), QSettings.Format.IniFormat)
    settings.setValue("destination", str(tmp_path / "downloads"))
    # Quick mode auto-saves regardless of the full window's optional auto-single setting.
    settings.setValue("auto_single", False)
    window = QuickWindow(settings, notify=lambda *args: events.append(args), tray_available=False)
    qtbot.addWidget(window)
    yield window, events
    window.exit_timer.stop()
    if window.worker:
        window.cancel()
        qtbot.waitUntil(lambda: window.worker is None)
    window.close()


@pytest.mark.parametrize(
    "text,expected",
    [
        (" https://instagram.com/reels/abc/\n", "https://instagram.com/reels/abc/"),
        ("https://youtube.com/watch?v=abc&list=all", "https://youtube.com/watch?v=abc"),
        ("some private text with https://example.org", ""),
        ("https://example.org\nhttps://other.org", ""),
        ("https://user:password@example.org", ""),
        ("file:///etc/passwd", ""),
        ("", ""),
    ],
)
def test_clipboard_accepts_only_one_complete_url(text, expected):
    assert clipboard_url(text) == expected


def test_empty_clipboard_shows_only_input(quick, qtbot, monkeypatch):
    window, events = quick

    class EmptyClipboard:
        def text(self):
            return "not a URL"

    monkeypatch.setattr(QApplication, "clipboard", lambda: EmptyClipboard())
    window.start_from_clipboard()
    qtbot.wait(200)
    assert window.isVisible() and window.url.isVisible()
    assert not window.status.isVisible() and not window.progress.isVisible()
    assert not window.cancel_button.isVisible()
    assert window.worker is None and not events


def test_clipboard_starts_download_all_notifies_and_reveals(quick, qtbot, tmp_path, monkeypatch):
    window, events = quick
    a, b = media(), media("two", kind="video")
    calls = []

    class Clipboard:
        def text(self):
            return "https://instagram.com/p/post/"

    monkeypatch.setattr(QApplication, "clipboard", lambda: Clipboard())

    def inspect(service, url, allow):
        assert events and events[0][0] == "MediaGrab started"
        calls.append(("inspect", url))
        return Inspection([a, b])

    paths = [tmp_path / "image.jpg", tmp_path / "video.mp4"]
    for path in paths:
        path.write_bytes(b"media")

    def download(service, items, root, progress, allow):
        calls.append(("download", items, root, allow))
        return BatchResult(paths)

    monkeypatch.setattr(MediaService, "inspect", inspect)
    monkeypatch.setattr(MediaService, "download", download)
    monkeypatch.setattr(
        "mediagrab.gui.reveal_files",
        lambda paths: calls.append(("reveal", paths)) or RevealResult(True, "Selected files"),
    )
    window.start_from_clipboard()
    qtbot.waitUntil(lambda: window.batch is not None and window.worker is None)
    assert calls[1][1] == [a, b]
    assert calls[-1] == ("reveal", paths)
    assert events[-1][0] == "MediaGrab finished"
    assert "2 saved" in events[-1][1]
    assert not window.settings.value("auto_single", type=bool)


def test_enter_runs_without_clipboard(quick, qtbot, monkeypatch):
    window, _ = quick
    monkeypatch.setattr(
        MediaService,
        "inspect",
        lambda *args: (_ for _ in ()).throw(MediaError("access", "No media")),
    )
    window.show()
    window.url.setText("https://instagram.com/p/post/")
    qtbot.keyClick(window.url, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: window.worker is None)
    assert window.isVisible() and window.url.isEnabled()
    assert window.status.text() == "No media"


@pytest.mark.parametrize("destination", ["", "   "])
def test_blank_destination_uses_downloads_instead_of_working_directory(
    quick, qtbot, monkeypatch, tmp_path, destination
):
    window, _ = quick
    window.settings.setValue("destination", destination)
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home)
    roots = []
    monkeypatch.setattr(MediaService, "inspect", lambda *args: Inspection([media()]))

    def download(service, items, root, progress, allow):
        roots.append(root)
        return BatchResult()

    monkeypatch.setattr(MediaService, "download", download)
    window.url.setText("https://instagram.com/p/post/")
    window.start()
    qtbot.waitUntil(lambda: window.batch is not None and window.worker is None)
    assert roots == [str(home / "Downloads/Media")]


def test_collection_requires_explicit_consent(quick, qtbot, monkeypatch):
    window, _ = quick
    calls, questions = [], []

    def inspect(service, url, allow):
        calls.append(("inspect", allow))
        if not allow:
            raise CollectionRequired()
        return Inspection([media(collection=True)], collection=True)

    def confirm(title, text):
        questions.append(title)
        return len(questions) == 1  # Permit metadata only; decline download.

    window.confirm = confirm
    monkeypatch.setattr(MediaService, "inspect", inspect)
    monkeypatch.setattr(
        MediaService, "download", lambda *args: pytest.fail("Unconfirmed collection download")
    )
    window.url.setText("https://youtube.com/playlist?list=all")
    window.start()
    qtbot.waitUntil(lambda: len(questions) == 2 and window.worker is None)
    assert calls == [("inspect", False), ("inspect", True)]
    assert "skipped" in window.status.text()


def test_cancel_while_background_inspection_keeps_event_loop_alive(quick, qtbot, monkeypatch):
    window, events = quick

    def inspect(service, *args):
        while not service.runner.cancel.is_set():
            time.sleep(0.01)
        service.runner.check()

    monkeypatch.setattr(MediaService, "inspect", inspect)
    window.url.setText("https://instagram.com/p/post/")
    window.start()
    window.cancel()
    qtbot.waitUntil(lambda: window.worker is None)
    assert window.url.isEnabled()
    assert events[-1][0] == "MediaGrab cancelled"


def test_partial_success_still_revealed_and_failure_visible(quick, qtbot, tmp_path, monkeypatch):
    window, events = quick
    result = BatchResult([tmp_path / "saved.jpg"], ["Other entry failed"])
    result.paths[0].write_bytes(b"image")
    revealed = []
    monkeypatch.setattr(MediaService, "inspect", lambda *args: Inspection([media(), media("two")]))
    monkeypatch.setattr(MediaService, "download", lambda *args: result)
    monkeypatch.setattr(
        "mediagrab.gui.reveal_files",
        lambda paths: revealed.extend(paths) or RevealResult(True, "Selected"),
    )
    window.url.setText("https://instagram.com/p/post/")
    window.start()
    qtbot.waitUntil(lambda: window.batch is not None and window.worker is None)
    assert revealed == result.paths
    assert window.isVisible() and "Other entry failed" in window.status.text()
    assert events[-1][2] is True


def test_background_tray_mode_hides_the_input(qtbot, tmp_path, monkeypatch):
    window = QuickWindow(
        QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat),
        notify=lambda *args: None,
        tray_available=True,
    )
    qtbot.addWidget(window)
    monkeypatch.setattr(window.tray, "show", lambda: None)

    def inspect(service, *args):
        while not service.runner.cancel.is_set():
            time.sleep(0.01)
        service.runner.check()

    monkeypatch.setattr(MediaService, "inspect", inspect)
    window.show()
    window.url.setText("https://instagram.com/p/post/")
    window.start()
    assert not window.isVisible()
    window.cancel()
    qtbot.waitUntil(lambda: window.worker is None)
    window.close()
