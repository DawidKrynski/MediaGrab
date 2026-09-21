"""Install into a disposable desktop-menu directory, never the real user profile."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest


def test_desktop_entry_supports_checkout_paths_with_reserved_characters(tmp_path):
    validator = shutil.which("desktop-file-validate")
    if not validator:
        pytest.skip("desktop-file-validate is required to validate menu entries")
    project = tmp_path / 'MediaGrab space $dollar "quote" `tick` %percent \\backslash'
    scripts = project / "scripts"
    scripts.mkdir(parents=True)
    installer = scripts / "install-desktop.sh"
    shutil.copyfile(Path(__file__).parents[1] / "scripts/install-desktop.sh", installer)
    data = tmp_path / "data"
    subprocess.run(
        ["bash", str(installer)],
        env=dict(os.environ, XDG_DATA_HOME=str(data)),
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess.run(
        [validator, str(data / "applications/mediagrab.desktop")],
        capture_output=True,
        text=True,
        check=True,
    )
