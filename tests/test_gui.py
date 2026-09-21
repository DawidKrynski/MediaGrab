import sys
import time
from pathlib import Path

from PySide6.QtCore import QSettings, Qt

from mediagrab.gui import MainWindow
from mediagrab.models import BatchResult, Inspection, MediaItem
from mediagrab.service import MediaService


def media(key="1"):
    return MediaItem(key, "ytdlp", "youtube", key, "Test media", "video", "https://youtu.be/" + key)


def test_gui_single_multiple_and_preferences(qtbot, tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings)
    qtbot.addWidget(window)
    window.show()
    monkeypatch.setattr(MediaService, "inspect", lambda *a, **k: Inspection([media()]))
    window.url.setText("https://youtu.be/1")
    qtbot.keyClick(window.url, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: window.worker is None)
    assert len(window.selected()) == 1 and window.download_button.isEnabled()
    window.on_inspected(Inspection([media(), media("2")]))
    assert not window.selected()
    qtbot.mouseClick(window.select_all, Qt.MouseButton.LeftButton)
    assert len(window.selected()) == 2
    qtbot.mouseClick(window.select_none, Qt.MouseButton.LeftButton)
    assert not window.selected()
    window.auto.setChecked(True)
    window.destination.setText(str(tmp_path / "downloads"))
    window.save_preferences()
    assert settings.value("auto_single", type=bool)
    assert settings.value("destination") == str(tmp_path / "downloads")


def test_gui_download_partial_and_reveal(qtbot, tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings)
    qtbot.addWidget(window)
    window.destination.setText(str(tmp_path))
    window.on_inspected(Inspection([media()]))
    file = tmp_path / "finished.mp4"
    file.write_bytes(b"video")
    monkeypatch.setattr(
        MediaService, "download", lambda *a, **k: BatchResult([file], ["Other item failed"])
    )
    calls = []
    from mediagrab.reveal import RevealResult

    monkeypatch.setattr(
        "mediagrab.gui.reveal_files",
        lambda paths: calls.append(paths) or RevealResult(True, "Selected"),
    )
    window.download()
    qtbot.waitUntil(lambda: window.worker is None)
    assert calls == [[file]]
    assert "1 failed" in window.status.text()
    assert "Selected" in window.details.toPlainText()


def test_blank_destination_restores_default_and_does_not_open_working_directory(
    qtbot, tmp_path, monkeypatch
):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("destination", " ")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    window = MainWindow(settings)
    qtbot.addWidget(window)
    assert window.destination.text() == str(tmp_path / "Downloads/Media")
    window.destination.clear()
    calls = []
    monkeypatch.setattr(window, "start_worker", lambda *args, **kwargs: calls.append(args))
    window.open_folder()
    assert not calls
    assert window.status.text() == "Choose a destination first."


def test_gui_stays_responsive_during_inspection_and_cancels(qtbot, tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings)
    qtbot.addWidget(window)

    def slow(service, *args):
        while not service.runner.cancel.is_set():
            time.sleep(0.02)
        service.runner.check()

    monkeypatch.setattr(MediaService, "inspect", slow)
    window.url.setText("https://youtu.be/1")
    window.inspect()
    assert window.cancel_button.isEnabled()
    qtbot.mouseClick(window.cancel_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.worker is None)
    assert window.inspect_button.isEnabled()
    assert "cancelled" in window.status.text().lower()


def test_explicit_cookies_copy_is_private_and_removed(qtbot, tmp_path, monkeypatch):
    cookie = tmp_path / "input-cookies.txt"
    original = b"# Netscape HTTP Cookie File\n"
    cookie.write_bytes(original)
    seen = []

    def inspect(service, *args):
        path = Path(service.adapters["ytdlp"].cookies)
        assert path != cookie
        if sys.platform != "win32":
            assert path.stat().st_mode & 0o777 == 0o600
        assert path.read_bytes() == original
        path.write_bytes(b"updated temporary jar")
        seen.append(path)
        return Inspection([media()])

    monkeypatch.setattr(MediaService, "inspect", inspect)
    window = MainWindow(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(window)
    window.cookies.setText(str(cookie))
    window.inspect()
    qtbot.waitUntil(lambda: window.worker is None)
    assert len(seen) == 1 and not seen[0].exists()
    assert cookie.read_bytes() == original


def test_gui_reports_instagram_empty_response_without_login_claim(qtbot, tmp_path, monkeypatch):
    from mediagrab.process import classify_error

    def unavailable(service, *args):
        raise classify_error(
            "ERROR: Instagram sent an empty media response. Use --cookies if needed."
        )

    monkeypatch.setattr(MediaService, "inspect", unavailable)
    window = MainWindow(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(window)
    window.url.setText("https://www.instagram.com/reels/example/")
    window.inspect()
    qtbot.waitUntil(lambda: window.worker is None)
    assert window.status.text().startswith("Access:")
    assert "expired" not in window.status.text()
    assert not window.download_button.isEnabled()
    assert window.inspect_button.isEnabled()
