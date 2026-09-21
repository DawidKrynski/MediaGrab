import json
import os
import sys
import time
from dataclasses import replace
from pathlib import Path
from threading import Event, Timer

import pytest

from mediagrab.backends import GalleryAdapter, YtDlpAdapter
from mediagrab.models import (
    Cancelled,
    CollectionRequired,
    MediaError,
    MediaItem,
    default_selection,
    selected_items,
)
from mediagrab.process import Output, Runner, classify_error
from mediagrab.reveal import reveal_files, reveal_message
from mediagrab.routing import is_single_url, route, source_name, validate_url
from mediagrab.service import MediaService
from mediagrab.storage import Store, contained, safe_component


def item(key="a", **kwargs):
    return MediaItem(
        key,
        "gallery",
        "instagram",
        key,
        "A readable title",
        "image",
        "https://www.instagram.com/p/test/",
        **kwargs,
    )


class FakeRunner:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = []
        self.cancel = Event()

    def check(self):
        if self.cancel.is_set():
            raise Cancelled()

    def run(self, args, **kwargs):
        self.calls.append(args)
        return next(self.outputs)


def output(value, code=0, error=""):
    return Output(json.dumps(value), error, code)


@pytest.mark.parametrize(
    "url,backend,source,single",
    [
        ("https://youtube.com/watch?v=abc&list=all", "ytdlp", "youtube", True),
        ("https://youtu.be/abc", "ytdlp", "youtube", True),
        ("https://instagram.com/p/abc/", "gallery", "instagram", True),
        ("https://x.com/user/status/123", "gallery", "x", True),
        ("https://twitter.com/user/status/123", "gallery", "x", True),
        ("https://tiktok.com/@user/photo/123", "gallery", "tiktok", True),
        ("https://reddit.com/r/test/comments/abc/title", "gallery", "reddit", True),
        ("https://facebook.com/watch?v=12", "ytdlp", "facebook", True),
        ("https://instagram.com/person", "gallery", "instagram", False),
        ("https://youtube.com/playlist?list=abc", "ytdlp", "youtube", False),
        (
            "https://youtube.com.evil.invalid/watch?v=abc",
            "ytdlp",
            "youtube-com-evil-invalid",
            False,
        ),
    ],
)
def test_routing(url, backend, source, single):
    assert route(url)[0] == backend
    assert source_name(url) == source
    assert is_single_url(url) is single


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "ftp://site/file", "--help", "https://u:p@site/video", "http://a/\nx"],
)
def test_invalid_url(url):
    with pytest.raises(MediaError):
        validate_url(url)


def test_playlist_removed_from_watch_url():
    assert (
        validate_url("https://youtube.com/watch?v=abc&list=all&index=2")
        == "https://youtube.com/watch?v=abc"
    )


def test_selection():
    a, b = item(), item("b")
    assert default_selection([a]) == {"a"}
    assert not default_selection([a, b])
    assert selected_items([a, b], {"b", "unknown"}) == [b]


def test_single_video_inspection():
    runner = FakeRunner(
        [output({"id": "abc", "title": "Demo", "extractor_key": "Youtube", "height": 1080})]
    )
    result = YtDlpAdapter(runner).inspect("https://youtube.com/watch?v=abc")
    assert len(result.items) == 1
    assert result.items[0].media_id == "abc"
    assert "1080" in result.items[0].quality
    assert "--skip-download" in runner.calls[0]
    assert "--ignore-config" in runner.calls[0]


def gallery_rows():
    return [
        [2, {"category": "instagram"}],
        [
            3,
            "https://cdn.invalid/a.jpg?expires=old",
            {"category": "instagram", "id": 42, "num": 1, "filename": "a", "extension": "jpg"},
        ],
        [
            3,
            "https://cdn.invalid/b.mp4",
            {"category": "instagram", "id": 42, "num": 2, "filename": "b", "extension": "mp4"},
        ],
    ]


def test_mixed_media_and_multi_image():
    rows = gallery_rows()
    result = GalleryAdapter(FakeRunner([output(rows)])).inspect("https://instagram.com/p/abc/")
    assert [i.kind for i in result.items] == ["image", "video"]
    assert len({i.key for i in result.items}) == 2
    rows[2][2]["extension"] = "png"
    result = GalleryAdapter(FakeRunner([output(rows)])).inspect("https://instagram.com/p/abc/")
    assert [i.kind for i in result.items] == ["image", "image"]


def test_gallery_selection_survives_reordering_and_signed_url_refresh(tmp_path):
    rows = gallery_rows()
    runner = FakeRunner(
        [
            output(rows),
            output([rows[0], rows[2], [3, "https://cdn.invalid/a.jpg?expires=new", rows[1][2]]]),
            Output("MGFILE:" + json.dumps(str(tmp_path / "media.jpg")) + "\n", "", 0),
        ]
    )
    adapter = GalleryAdapter(runner)
    selected = adapter.inspect("https://instagram.com/p/abc/").items[0]
    assert adapter.download(selected, tmp_path, lambda *_: None) == tmp_path / "media.jpg"
    expr = runner.calls[-1][runner.calls[-1].index("--filter") + 1]
    assert "num == 1" in expr and "filename == 'a'" in expr
    assert "--child-filter" in runner.calls[-1]
    assert "--Print" in runner.calls[-1]


def test_gallery_changed_selection_refused(tmp_path):
    runner = FakeRunner([output(gallery_rows()), output([gallery_rows()[2]])])
    adapter = GalleryAdapter(runner)
    selected = adapter.inspect("https://instagram.com/p/abc/").items[0]
    with pytest.raises(MediaError, match="changed or disappeared"):
        adapter.download(selected, tmp_path, lambda *_: None)
    assert len(runner.calls) == 2


def test_gallery_json_error_not_silent():
    adapter = GalleryAdapter(
        FakeRunner([output([[-1, {"error": "AuthenticationError", "message": "Login required"}]])])
    )
    with pytest.raises(MediaError) as exc:
        adapter.inspect("https://instagram.com/p/abc/")
    assert exc.value.kind == "login"


def test_queued_media_visible():
    rows = gallery_rows() + [[6, "https://youtu.be/abc", {"title": "Embedded video"}]]
    result = GalleryAdapter(FakeRunner([output(rows)])).inspect("https://instagram.com/p/abc/")
    assert result.items[-1].backend == "queued"
    assert result.items[-1].page_url == "https://youtu.be/abc"


def test_collection_requires_confirmation_before_network():
    runner = FakeRunner([])
    with pytest.raises(CollectionRequired):
        MediaService(runner).inspect("https://youtube.com/@channel")
    assert not runner.calls


def test_fallback_only_on_unsupported():
    runner = FakeRunner(
        [Output("", "Unsupported URL", 1), output({"id": "abc", "title": "Fallback"})]
    )
    result = MediaService(runner).inspect("https://instagram.com/p/abc/")
    assert result.items[0].backend == "ytdlp"
    assert len(runner.calls) == 2
    runner = FakeRunner([Output("", "429 Too Many Requests", 1)])
    with pytest.raises(MediaError) as exc:
        MediaService(runner).inspect("https://instagram.com/p/abc/")
    assert exc.value.kind == "rate_limit"
    assert len(runner.calls) == 1


@pytest.mark.parametrize(
    "text,kind",
    [
        ("Unsupported URL", "unsupported"),
        ("Login required", "login"),
        ("HTTP 429", "rate_limit"),
        ("Video unavailable", "unavailable"),
        ("ffmpeg not found", "dependency"),
        ("connection reset", "network"),
    ],
)
def test_error_categories(text, kind):
    assert classify_error(text).kind == kind


def test_sanitizing_and_path_containment(tmp_path):
    name = safe_component("../../a/b\\c\n%({bad}) ♥" + "ą" * 200)
    assert "/" not in name and "\\" not in name and "%" not in name
    assert len(name.encode()) <= 100
    with pytest.raises(MediaError):
        contained(tmp_path, tmp_path / ".." / "escape")
    (tmp_path / "link").symlink_to(tmp_path.parent, target_is_directory=True)
    with pytest.raises(MediaError):
        contained(tmp_path, tmp_path / "link" / "escape")


def test_duplicates_and_collision_preservation(tmp_path):
    root = tmp_path / "root"
    stage = tmp_path / "stage"
    stage.mkdir()
    media = stage / "media.mp4"
    media.write_bytes(b"video payload")
    store = Store(root)
    try:
        first = store.publish(item(), media, stage)
        assert store.existing("a") == first
        first.write_bytes(b"unrelated")
        assert store.existing("a") is None
        second = store.publish(item(), media, stage)
        assert second != first
        assert first.read_bytes() == b"unrelated"
        assert store.existing("a") == second
    finally:
        store.close()


def test_source_symlink_refused(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "instagram").symlink_to(tmp_path, target_is_directory=True)
    stage = tmp_path / "stage"
    stage.mkdir()
    file = stage / "x.jpg"
    file.write_bytes(b"x")
    store = Store(root)
    try:
        with pytest.raises(MediaError):
            store.publish(item(), file, stage)
    finally:
        store.close()


def test_partial_failure_preserves_success_and_cleanup(tmp_path):
    service = MediaService(FakeRunner([]))

    class Adapter:
        def download(self, item, stage, progress):
            if item.key == "bad":
                (stage / "unfinished.part").write_bytes(b"partial")
                raise MediaError("network", "Failed")
            path = stage / "final.jpg"
            path.write_bytes(b"successful")
            return path

    service.adapters["gallery"] = Adapter()
    result = service.download([item("good"), item("bad"), item("good2")], tmp_path)
    assert len(result.paths) == 2 and len(result.failures) == 1
    assert all(p.is_file() for p in result.paths)
    assert not list(tmp_path.glob(".mediagrab-work-*"))
    repeat = service.download([item("good")], tmp_path)
    assert repeat.skipped == 1 and repeat.paths == result.paths[:1]


def test_cancelled_batch_preserves_prior_success(tmp_path):
    runner = FakeRunner([])
    service = MediaService(runner)

    class Adapter:
        def download(self, item, stage, progress):
            if item.key == "second":
                runner.cancel.set()
                raise Cancelled()
            path = stage / "final.jpg"
            path.write_bytes(b"ok")
            return path

    service.adapters["gallery"] = Adapter()
    result = service.download([item(), item("second")], tmp_path)
    assert result.cancelled and len(result.paths) == 1
    assert not list(tmp_path.glob(".mediagrab-work-*"))


@pytest.mark.skipif(os.name == "nt", reason="Linux /proc assertion; native Windows coverage elsewhere")
def test_subprocess_cancellation_kills_descendant(tmp_path):
    pidfile = tmp_path / "child-pid"
    code = "import subprocess,time,sys; p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);open(sys.argv[1],'w').write(str(p.pid));time.sleep(60)"
    event = Event()
    timer = Timer(0.6, event.set)
    timer.start()
    start = time.monotonic()
    with pytest.raises(Cancelled):
        Runner(event).run([sys.executable, "-c", code, str(pidfile)])
    timer.join()
    assert time.monotonic() - start < 4
    pid = int(pidfile.read_text())
    stat = Path(f"/proc/{pid}/stat")
    assert not stat.exists() or stat.read_text().split()[2] == "Z"


def test_subprocess_timeout_and_pre_cancel():
    with pytest.raises(MediaError) as exc:
        Runner().run([sys.executable, "-c", "import time;time.sleep(60)"], timeout=0.2)
    assert exc.value.kind == "timeout"
    event = Event()
    event.set()
    with pytest.raises(Cancelled):
        Runner(event).run(["does-not-exist"])


@pytest.mark.skipif(os.name == "nt", reason="FileManager1 is a Linux integration")
def test_reveal_message_uses_encoded_absolute_uris(tmp_path):
    path = tmp_path / "two files #ą?.mp4"
    message = reveal_message([path, path])
    assert message.destination == "org.freedesktop.FileManager1"
    assert message.path == "/org/freedesktop/FileManager1"
    assert message.interface == "org.freedesktop.FileManager1"
    assert message.member == "ShowItems"
    assert message.signature == "ass"
    assert message.body == [[path.as_uri()], ""]
    assert "%20" in message.body[0][0] and "%23" in message.body[0][0]


@pytest.mark.skipif(os.name == "nt", reason="FileManager1 is a Linux integration")
def test_batch_reveal_and_fallback(tmp_path):
    paths = [tmp_path / "a.jpg", tmp_path / "b.mp4"]
    for path in paths:
        path.touch()
    messages, folders = [], []

    def sender(message):
        messages.append(message)
        return True

    assert reveal_files(paths, sender, folders.append).selected
    assert len(messages) == 1 and len(messages[0].body[0]) == 2 and not folders
    result = reveal_files(paths, lambda _: False, folders.append)
    assert not result.selected and "selection was unavailable" in result.message
    assert folders == [tmp_path]


def test_collection_download_guard(tmp_path):
    service = MediaService(FakeRunner([]))
    result = service.download([replace(item(), collection=True)], tmp_path)
    assert not result.paths and "[collection]" in result.failures[0]


@pytest.mark.parametrize("destination", ["", "   "])
def test_empty_download_root_refused_before_creating_files(tmp_path, monkeypatch, destination):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(MediaError, match="Choose a destination"):
        MediaService(FakeRunner([])).download([item()], destination)
    assert not list(tmp_path.iterdir())


def test_embedded_video_is_inspected_alongside_images():
    rows = [gallery_rows()[1], [6, "https://youtu.be/abc", {"title": "Embedded"}]]
    runner = FakeRunner(
        [output(rows), output({"id": "abc", "title": "Video", "extractor_key": "Youtube"})]
    )
    result = MediaService(runner).inspect("https://reddit.com/r/test/comments/abc/title")
    assert [i.kind for i in result.items] == ["image", "video"]
    assert all(i.source == "reddit" for i in result.items)
    assert result.items[1].backend == "ytdlp"


def test_unsupported_link_both_engines():
    runner = FakeRunner([Output("", "Unsupported URL", 1), Output("", "Unsupported URL", 1)])
    with pytest.raises(MediaError) as exc:
        MediaService(runner).inspect("https://unsupported.invalid/post", True)
    assert exc.value.kind == "unsupported"
    assert len(runner.calls) == 2


def test_generic_identity_namespaces_urls():
    outputs = [output({"id": "video", "extractor_key": "Generic"})] * 2
    adapter = YtDlpAdapter(FakeRunner(outputs))
    a = adapter.inspect("https://example.org/a/video.mp4", True).items[0]
    b = adapter.inspect("https://example.org/b/video.mp4", True).items[0]
    assert a.key != b.key


def test_gallery_warning_preserves_success():
    rows = [gallery_rows()[1], [-1, {"message": "HTTP 429"}]]
    result = GalleryAdapter(FakeRunner([output(rows)])).inspect("https://instagram.com/p/abc/")
    assert len(result.items) == 1 and "limiting requests" in result.warnings[0]


def test_yt_final_paths_not_guessed_and_selection_filtered(tmp_path):
    final = tmp_path / "actual-merged.webm"
    runner = FakeRunner([Output("MGFILE:" + json.dumps(str(final)), "", 0)])
    adapter = YtDlpAdapter(runner)
    selected = replace(item(), backend="ytdlp", selector={"id": "a", "index": 2})
    assert adapter.download(selected, tmp_path, lambda *_: None) == final
    call = runner.calls[0]
    assert call[call.index("--playlist-items") + 1] == "2"
    assert call[call.index("--match-filters") + 1] == 'id = "a"'
    assert "after_move:MGFILE:%(filepath)j" in call


def test_store_lock_rejects_concurrent_writer(tmp_path):
    first = Store(tmp_path)
    try:
        with pytest.raises(MediaError) as exc:
            Store(tmp_path)
        assert exc.value.kind == "busy"
    finally:
        first.close()


@pytest.mark.parametrize("path", ["reel/abc/", "reels/abc/", "tv/abc/"])
def test_instagram_video_urls_use_video_engine(path):
    url = "https://www.instagram.com/" + path
    assert route(url) == ("ytdlp", "gallery")
    assert is_single_url(url)


@pytest.mark.parametrize("path", ["p/abc/", "profile/reels/", "reels/audio/123/"])
def test_instagram_other_urls_still_use_gallery(path):
    assert route("https://www.instagram.com/" + path)[0] == "gallery"


def test_instagram_empty_response_is_not_misreported_as_login():
    error = classify_error(
        "WARNING: No CSRF token set by Instagram API\n"
        "ERROR: [Instagram] ID: Instagram sent an empty media response. "
        "Check if this post is accessible in your browser without being logged-in. "
        "If it is not, then use --cookies. See how to pass cookies."
    )
    assert error.kind == "access"
    assert "expired" not in str(error)


def test_warning_cookie_hint_does_not_override_terminal_network_error():
    error = classify_error("WARNING: See cookies documentation\nERROR: Connection reset")
    assert error.kind == "network"


def test_instagram_anonymous_rate_limit_is_not_login_error():
    error = classify_error(
        "ERROR: The webpage request was redirected to the login page. "
        "You have exceeded the rate-limit for accessing posts anonymously"
    )
    assert error.kind == "rate_limit"


def test_reel_inspection_does_not_require_gallery_authentication():
    runner = FakeRunner([output({"id": "reel-id", "extractor_key": "Instagram", "title": "Reel"})])
    result = MediaService(runner).inspect("https://www.instagram.com/reels/reel-id/")
    assert result.items[0].backend == "ytdlp"
    assert len(runner.calls) == 1 and "yt_dlp" in runner.calls[0]
