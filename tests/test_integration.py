"""Opt-in real CLI contract tests. HTTP binds only to loopback; no public network."""

import base64
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import shutil
import subprocess
from threading import Thread

import pytest

from mediagrab.backends import GalleryAdapter, YtDlpAdapter
from mediagrab.process import Runner
from mediagrab.service import MediaService

pytestmark = pytest.mark.integration


@pytest.fixture
def local_media(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg required for integration media fixture")
    (tmp_path / "image.png").write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
        )
    )
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=160x90:d=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-shortest",
            str(tmp_path / "tiny.mp4"),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(tmp_path / "tiny.mp4"),
            "-map",
            "0",
            "-c",
            "copy",
            "-f",
            "dash",
            "stream.mpd",
        ],
        cwd=tmp_path,
        check=True,
    )
    assert list(tmp_path.glob("init-stream*.m4s"))
    assert list(tmp_path.glob("chunk-stream*.m4s"))

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(tmp_path)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", tmp_path
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_real_gallery_inspect_selected_download_final_path(local_media, tmp_path):
    url, files = local_media
    adapter = GalleryAdapter(Runner())
    inspection = adapter.inspect(url + "/image.png", allow_collection=True)
    assert len(inspection.items) == 1
    stage = tmp_path / "gallery-stage"
    stage.mkdir()
    actual = adapter.download(inspection.items[0], stage, lambda *_: None)
    assert actual.is_file() and actual.parent.samefile(stage)
    assert actual.read_bytes() == (files / "image.png").read_bytes()


@pytest.mark.parametrize("filename", ["tiny.mp4", "stream.mpd"])
def test_real_ytdlp_inspection_download_merge_publish_and_duplicate(
    local_media, tmp_path, filename
):
    url, _ = local_media
    runner = Runner()
    adapter = YtDlpAdapter(runner)
    inspection = adapter.inspect(url + "/" + filename, allow_collection=True)
    assert len(inspection.items) == 1
    service = MediaService(runner)
    root = tmp_path / "download-root"
    result = service.download(inspection.items, root, allow_collection=True)
    assert not result.failures, result.failures
    assert len(result.paths) == 1 and result.paths[0].is_file()
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            str(result.paths[0]),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "video" in probe.stdout and "audio" in probe.stdout
    repeat = service.download(inspection.items, root, allow_collection=True)
    assert repeat.skipped == 1 and repeat.paths == result.paths
    assert not list(root.glob(".mediagrab-work-*"))


def test_real_ytdlp_multi_video_selection(local_media, tmp_path):
    url, files = local_media
    shutil.copyfile(files / "tiny.mp4", files / "second.mp4")
    (files / "collection.html").write_text(
        '<html><title>Collection</title><video src="tiny.mp4"></video><video src="second.mp4"></video></html>'
    )
    adapter = YtDlpAdapter(Runner())
    result = adapter.inspect(url + "/collection.html", allow_collection=True)
    assert len(result.items) == 2
    stage = tmp_path / "selected-stage"
    stage.mkdir()
    actual = adapter.download(result.items[1], stage, lambda *_: None)
    assert actual.is_file()
    assert len(list(stage.glob("*.mp4"))) == 1


def test_real_quick_gui_auto_saves_and_reveals(local_media, tmp_path, qtbot, monkeypatch):
    from PySide6.QtCore import QSettings
    from mediagrab.quick import QuickWindow
    from mediagrab.reveal import RevealResult

    url, files = local_media
    settings = QSettings(str(tmp_path / "quick.ini"), QSettings.Format.IniFormat)
    settings.setValue("destination", str(tmp_path / "quick-downloads"))
    settings.setValue("auto_single", False)
    notices, reveals = [], []
    window = QuickWindow(settings, notify=lambda *args: notices.append(args), tray_available=False)
    qtbot.addWidget(window)
    monkeypatch.setattr(
        "mediagrab.gui.reveal_files",
        lambda paths: reveals.append(paths) or RevealResult(True, "Selected files"),
    )
    window.url.setText(url + "/image.png")
    window.start()
    qtbot.waitUntil(lambda: window.batch is not None and window.worker is None, timeout=15000)
    window.exit_timer.stop()
    assert not window.batch.failures
    assert len(window.batch.paths) == 1
    assert window.batch.paths[0].read_bytes() == (files / "image.png").read_bytes()
    assert reveals == [window.batch.paths]
    assert notices[0][0] == "MediaGrab started"
    assert notices[-1][0] == "MediaGrab finished"
