"""Real child-process and filesystem checks, including native Windows branches."""

import os
from pathlib import Path
import subprocess
import sys
from threading import Event, Thread
import time
from types import SimpleNamespace

import pytest

from mediagrab.models import Cancelled, MediaError
from mediagrab.process import Runner
from mediagrab.storage import (
    Store, contained, is_link_or_reparse_point, safe_component, windows_path_name,
)


def process_alive(pid):
    if os.name != "nt":
        status = Path(f"/proc/{pid}/stat")
        return status.exists() and status.read_text().split()[2] != "Z"
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if not handle:
        assert ctypes.get_last_error() == 87  # PID no longer exists, not access denied.
        return False
    try:
        result = kernel.WaitForSingleObject(handle, 0)
        assert result in (0, 258)  # signaled / WAIT_TIMEOUT
        return result == 258
    finally:
        kernel.CloseHandle(handle)


CHILD_COMMAND = (
    "import subprocess,sys,time; from pathlib import Path; "
    "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
    "Path(sys.argv[1]).write_text(str(child.pid)); "
)


def assert_child_stopped(pidfile):
    assert pidfile.is_file(), "Child did not start; process cleanup was not exercised"
    pid = int(pidfile.read_text())
    deadline = time.monotonic() + 3
    while process_alive(pid) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not process_alive(pid), "The downloader's child survived cleanup"


def test_cancel_kills_real_child_process_on_both_platforms(tmp_path):
    pidfile = tmp_path / "child-pid"
    cancelled = Event()

    def cancel_after_child_started():
        deadline = time.monotonic() + 5
        while not pidfile.is_file() and time.monotonic() < deadline:
            time.sleep(0.02)
        cancelled.set()

    watcher = Thread(target=cancel_after_child_started, daemon=True)
    watcher.start()
    try:
        with pytest.raises(Cancelled):
            Runner(cancelled).run(
                [sys.executable, "-c", CHILD_COMMAND + "time.sleep(60)", str(pidfile)],
                timeout=8,
            )
    finally:
        watcher.join(timeout=6)
    assert_child_stopped(pidfile)


def test_timeout_kills_child_after_parent_exited_with_inherited_pipes(tmp_path):
    pidfile = tmp_path / "child-pid"
    with pytest.raises(MediaError) as error:
        Runner().run([sys.executable, "-c", CHILD_COMMAND, str(pidfile)], timeout=2)
    assert error.value.kind == "timeout"
    assert_child_stopped(pidfile)


def test_pipe_reader_drains_both_streams_and_preserves_progress(monkeypatch):
    # Exercise the Windows reader on Linux too; native Windows runs additionally
    # exercise Job Objects and Windows anonymous pipe handles.
    import mediagrab.process as process

    original = process.pipe_events
    monkeypatch.setattr(process, "pipe_events", lambda proc, **kw: original(proc, threaded=True))
    lines = []
    result = Runner().run(
        [sys.executable, "-c", "import sys; print('progress'); sys.stderr.write('error-line\\n')"],
        on_line=lines.append,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "progress"
    assert result.stderr.strip() == "error-line"
    assert sorted(lines) == ["error-line", "progress"]


def test_threaded_reader_enforces_output_limit_and_stops_noisy_process(monkeypatch):
    import mediagrab.process as process

    original = process.pipe_events
    monkeypatch.setattr(process, "pipe_events", lambda proc, **kw: original(proc, threaded=True))
    monkeypatch.setattr(process, "MAX_OUTPUT_BYTES", 65536)
    with pytest.raises(MediaError) as error:
        Runner().run(
            [sys.executable, "-c", "import os\nwhile True: os.write(1, b'x' * 65536)"],
            timeout=5,
        )
    assert error.value.kind == "limit"


def test_engine_protocol_stays_utf8_when_parent_requests_legacy_encoding(monkeypatch):
    monkeypatch.setenv("PYTHONIOENCODING", "cp1252")
    monkeypatch.setenv("PYTHONUTF8", "0")
    text = "Zażółć gęślą jaźń — 日本語"
    lines = []
    result = Runner().run(
        [sys.executable, "-c", f"import sys; print({text!r}); sys.stderr.write({text!r})"],
        on_line=lines.append,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == text
    assert result.stderr == text
    assert lines == [text]
    assert os.environ["PYTHONIOENCODING"] == "cp1252"
    assert os.environ["PYTHONUTF8"] == "0"


@pytest.mark.parametrize("name", ["CON", "nul.jpg", "AuX", "COM1", "COM¹", "LPT9.png", "PRN"])
def test_reserved_windows_components_are_portable(name):
    result = safe_component(name)
    assert result.startswith("_")
    assert not result.endswith((" ", "."))
    assert len(result.encode()) <= 100


@pytest.mark.parametrize(
    "source,expected",
    [
        ("//?/C:/stage/media.jpg", "C:\\stage\\media.jpg"),
        ("\\\\?\\C:\\stage\\media.jpg", "C:\\stage\\media.jpg"),
        ("//?/UNC/server/share/media.jpg", "\\\\server\\share\\media.jpg"),
        ("\\\\?\\UNC\\server\\share\\media.jpg", "\\\\server\\share\\media.jpg"),
        ("//server/share/media.jpg", "\\\\server\\share\\media.jpg"),
    ],
)
def test_windows_extended_paths_keep_drive_and_unc_semantics(source, expected):
    assert windows_path_name(source) == expected


@pytest.mark.parametrize("path", ["//./PhysicalDrive0", "//?/GLOBALROOT/Device/HarddiskVolume1"])
def test_windows_device_namespaces_are_refused(path):
    with pytest.raises(MediaError, match="device namespace"):
        windows_path_name(path)


@pytest.mark.skipif(os.name != "nt", reason="Requires native Windows path resolution")
def test_windows_extended_output_is_contained_and_siblings_still_rejected(tmp_path):
    output = tmp_path / "media.jpg"
    output.write_bytes(b"fixture")
    extended = Path("//?/" + str(output).replace("\\", "/"))
    assert contained(tmp_path, extended) == output.resolve()
    sibling = tmp_path.with_name(tmp_path.name + "-outside") / "media.jpg"
    with pytest.raises(MediaError, match="Unsafe"):
        contained(tmp_path, Path("//?/" + str(sibling).replace("\\", "/")))


def test_reparse_attribute_is_rejected_even_without_symlink_mode(monkeypatch, tmp_path):
    path = tmp_path / "junction"
    monkeypatch.setattr(Path, "lstat", lambda self: SimpleNamespace(st_mode=0, st_file_attributes=0x400))
    assert is_link_or_reparse_point(path)


@pytest.mark.skipif(os.name != "nt", reason="Requires a real Windows junction")
def test_windows_junction_is_refused_even_when_it_points_inside_destination(tmp_path):
    target = tmp_path / "real"
    target.mkdir()
    junction = tmp_path / "junction"
    subprocess.run(
        f'cmd.exe /d /c mklink /J "{junction}" "{target}"',
        capture_output=True, check=True,
    )
    try:
        with pytest.raises(MediaError, match="reparse"):
            contained(tmp_path, junction / "media.jpg")
    finally:
        junction.rmdir()


def test_destination_lock_is_released_and_can_be_reopened(tmp_path):
    first = Store(tmp_path)
    try:
        with pytest.raises(MediaError) as error:
            Store(tmp_path)
        assert error.value.kind == "busy"
    finally:
        first.close()
    reopened = Store(tmp_path)
    reopened.close()
