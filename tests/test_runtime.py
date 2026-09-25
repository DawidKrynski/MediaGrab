"""Helper-process commands for source installations and the portable build."""

from pathlib import Path
import sys

import pytest

from mediagrab import engine, runtime
from mediagrab.backends import GalleryAdapter, YtDlpAdapter


def test_source_installation_uses_its_interpreter(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert runtime.engine_command("yt_dlp") == [sys.executable, "-m", "yt_dlp"]
    assert runtime.application_command("--advanced") == [
        sys.executable, "-m", "mediagrab", "--advanced"
    ]
    assert YtDlpAdapter(None).base()[:3] == [sys.executable, "-m", "yt_dlp"]
    assert GalleryAdapter(None).base()[:3] == [sys.executable, "-m", "gallery_dl"]


def test_portable_build_uses_the_sibling_engine_helper(monkeypatch, tmp_path):
    app = tmp_path / "MediaGrab" / "MediaGrab.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(app))
    helper = str(app.with_name("mediagrab-engine.exe"))
    assert runtime.helper_python() == helper
    assert runtime.engine_command("gallery_dl") == [helper, "-m", "gallery_dl"]
    assert runtime.application_command("--advanced") == [str(app), "--advanced"]
    assert YtDlpAdapter(None).base()[:3] == [helper, "-m", "yt_dlp"]


def test_engine_command_refuses_unknown_modules():
    with pytest.raises(ValueError):
        runtime.engine_command("pip")


@pytest.mark.parametrize(
    "argv",
    [[], ["-m"], ["-m", "pip", "install", "x"], ["-c", "print(1)"], ["script.py"], ["-m", "os"]],
)
def test_engine_helper_is_not_a_general_interpreter(argv, capsys):
    assert engine.main(argv) == 2
    assert "internal helper" in capsys.readouterr().err


def test_engine_helper_runs_a_bundled_engine_module(monkeypatch):
    calls = []

    def run_module(name, run_name, alter_sys):
        calls.append((name, run_name, alter_sys, list(sys.argv)))

    monkeypatch.setattr(engine.runpy, "run_module", run_module)
    monkeypatch.setattr(sys, "argv", ["mediagrab-engine.exe"])
    assert engine.main(["-m", "yt_dlp", "--version"]) == 0
    assert calls == [("yt_dlp", "__main__", True, ["yt_dlp", "--version"])]


def test_bootstrap_is_shared_with_the_windows_launcher():
    source = (Path(runtime.__file__).with_name("_windows.py")).read_text(encoding="utf-8")
    assert "runtime.helper_python()" in source and "runtime.BOOTSTRAP" in source
    assert "CREATE_NO_WINDOW" in runtime.BOOTSTRAP
