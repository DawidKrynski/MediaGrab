"""Restrict temporary authentication files before any credentials are copied."""

import csv
import os
from pathlib import Path
import re
import subprocess
import sys

from .models import MediaError


def protect_private_directory(path):
    if sys.platform != "win32":
        os.chmod(path, 0o700)
        return
    system = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    options = dict(
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        creationflags=0x08000000,
    )
    try:
        identity = subprocess.run(
            [str(system / "whoami.exe"), "/user", "/fo", "csv", "/nh"], **options
        )
        records = list(csv.reader(identity.stdout.splitlines()))
        if len(records) != 1 or len(records[0]) != 2:
            raise ValueError("Unexpected identity format")
        sid = records[0][1].strip()
        if not re.fullmatch(r"S-1-(?:\d+-)*\d+", sid):
            raise ValueError("Invalid Windows identity")
        # The directory is still empty. Remove any explicit creator/default ACEs
        # before replacing inherited access with the current user only.
        subprocess.run([str(system / "icacls.exe"), str(path), "/reset"], **options)
        subprocess.run(
            [
                str(system / "icacls.exe"),
                str(path),
                "/inheritance:r",
                "/grant:r",
                f"*{sid}:(OI)(CI)F",
            ],
            **options,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        raise MediaError(
            "cookies", "Could not secure the temporary cookies directory. No cookies were copied."
        ) from None
