"""Defaults shared by the quick launcher and the full window."""

from pathlib import Path


def download_destination(settings) -> str:
    value = str(settings.value("destination", "") or "")
    # An empty edited preference must never turn into the process working directory.
    return value if value.strip() else str(Path.home() / "Downloads/Media")
