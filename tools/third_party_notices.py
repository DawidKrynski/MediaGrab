"""Collect notices and copyleft sources for the portable Windows package.

Run with the build environment's Python after installing MediaGrab into it:

    python tools/third_party_notices.py build/windows

Writes THIRD_PARTY_NOTICES.txt (inventory, full license texts, source locations)
and downloads the source distributions of bundled copyleft Python packages into
sources/, verifying the SHA-256 digests published by PyPI. Only runtime
dependencies of MediaGrab plus the PyInstaller bootloader are listed; test tools
are not bundled.
"""

import hashlib
import json
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
import re
import sys
import urllib.request

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

# Bundled packages whose licenses require corresponding source with object code.
SOURCE_PACKAGES = {"gallery-dl", "mutagen", "certifi"}
# Components shipped as binaries whose source is not available on PyPI.
UPSTREAM_SOURCES = {
    "pyside6-essentials": "https://download.qt.io/official_releases/QtForPython/pyside6/",
    "shiboken6": "https://download.qt.io/official_releases/QtForPython/shiboken6/",
}
QT_SOURCE = "https://download.qt.io/archive/qt/"
BUILD_TOOLS = ["pyinstaller"]
# Qt for Python wheels carry no license files; ship the texts of the chosen LGPL path.
VENDORED = Path(__file__).with_name("windows") / "licenses"
VENDORED_LICENSES = {
    key: ["LGPL-3.0.txt", "GPL-3.0.txt"]
    for key in ("pyside6", "pyside6-essentials", "pyside6-addons", "shiboken6")
}
# Native payloads whose wheels ship no license texts for their statically linked code.
VENDORED_EXTRA = {"curl-cffi": ["curl_cffi-native.txt"]}
LICENSE_NAME = re.compile(r"(licen[cs]e|copying|notice|authors)", re.IGNORECASE)


def requirements(dist, extras=()):
    for text in dist.requires or ():
        requirement = Requirement(text)
        marker = requirement.marker
        if marker is None or any(
            marker.evaluate({"extra": extra}) for extra in (*extras, "")
        ):
            yield requirement


def runtime_closure(root):
    found, pending = {}, [(root, ())]
    while pending:
        name, extras = pending.pop()
        key = canonicalize_name(name)
        try:
            dist = distribution(name)
        except PackageNotFoundError:
            continue
        if key in found and not extras:
            continue
        found[key] = dist
        for requirement in requirements(dist, extras):
            pending.append((requirement.name, tuple(requirement.extras)))
    return found


def license_label(dist):
    meta = dist.metadata
    if meta.get("License-Expression"):
        return meta["License-Expression"]
    classifiers = [
        value.split("::")[-1].strip()
        for value in meta.get_all("Classifier") or ()
        if value.startswith("License ::")
    ]
    if classifiers:
        return "; ".join(classifiers)
    return (meta.get("License") or "see license files").splitlines()[0][:120]


def license_texts(dist):
    for file in dist.files or ():
        if file.suffix in {".py", ".pyc", ".pyi"}:
            continue
        if any(LICENSE_NAME.search(part) for part in file.parts[-2:]):
            path = Path(dist.locate_file(file))
            if path.is_file() and path.stat().st_size < 2_000_000:
                yield file, path.read_text(encoding="utf-8", errors="replace")


def embedded_notices(dist):
    """Leading /*! ... */ license headers of bundled JavaScript files."""
    for file in dist.files or ():
        if file.suffix == ".js":
            text = Path(dist.locate_file(file)).read_text(encoding="utf-8", errors="replace")
            match = re.match(r"\s*(/\*!.*?\*/)", text, re.DOTALL)
            if match:
                yield f"{file} (embedded header)", match.group(1)


def download_sdist(name, version, target):
    with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=60) as r:
        release = json.load(r)
    sdists = [item for item in release["urls"] if item["packagetype"] == "sdist"]
    if len(sdists) != 1:
        raise RuntimeError(f"Expected one source distribution for {name} {version}")
    item = sdists[0]
    with urllib.request.urlopen(item["url"], timeout=120) as r:
        data = r.read()
    if hashlib.sha256(data).hexdigest() != item["digests"]["sha256"]:
        raise RuntimeError(f"Source distribution digest mismatch for {name} {version}")
    (target / item["filename"]).write_bytes(data)
    return item["filename"], item["url"], item["digests"]["sha256"]


def main(output):
    output.mkdir(parents=True, exist_ok=True)
    sources = output / "sources"
    sources.mkdir(exist_ok=True)
    bundled = runtime_closure("mediagrab")
    bundled.pop("mediagrab", None)
    tools = {canonicalize_name(name): distribution(name) for name in BUILD_TOOLS}
    everything = dict(sorted({**bundled, **tools}.items()))

    header = [
        "MediaGrab portable Windows package - third-party notices",
        "",
        "MediaGrab's own code is MIT licensed (LICENSE.txt). The components below are",
        "included in this package under their own licenses, which govern. This file",
        "lists them, reproduces their license files, and says where their source is.",
        "External programs (FFmpeg, ffprobe, Deno, Node.js) are not included.",
        "",
        f"Python {sys.version.split()[0]} (Python Software Foundation License; the",
        "Windows build includes OpenSSL, libffi, bzip2, xz, zlib, SQLite and the",
        "Microsoft Visual C++ runtime DLLs; see the Python license text below).",
        "",
        "Bundled Python distributions:",
    ]
    for key, dist in everything.items():
        role = " (bootloader only)" if key in tools else ""
        header.append(
            f"  {dist.metadata['Name']} {dist.version}: {license_label(dist)}{role}"
        )

    source_lines = ["", "=" * 78, "Corresponding source", ""]
    for key, dist in bundled.items():
        if key in SOURCE_PACKAGES:
            filename, url, digest = download_sdist(dist.metadata["Name"], dist.version, sources)
            source_lines.append(
                f"{dist.metadata['Name']} {dist.version}: sources/{filename}\n"
                f"  from {url}\n  sha256 {digest}"
            )
    pyside = bundled.get("pyside6-essentials")
    if pyside is not None:
        source_lines += [
            f"Qt for Python (PySide6 / shiboken6) {pyside.version}: "
            f"{UPSTREAM_SOURCES['pyside6-essentials']}{pyside.version}/ and "
            f"{UPSTREAM_SOURCES['shiboken6']}{pyside.version}/",
            f"Qt {pyside.version} libraries: {QT_SOURCE}"
            f"{'.'.join(pyside.version.split('.')[:2])}/{pyside.version}/",
            "The Qt libraries are separate DLL files in _internal/PySide6 and can be",
            "replaced with compatible builds of your own (LGPL-3.0 section 4).",
        ]
    source_lines += [
        "The remaining bundled Python packages are permissively licensed; their",
        "sources are published on https://pypi.org under the listed versions.",
    ]

    sections = []
    for key, dist in everything.items():
        texts = list(license_texts(dist))
        if not texts and key in VENDORED_LICENSES:
            if key != "pyside6-essentials":
                texts = [("(see PySide6 Essentials)", "")]
            else:
                texts = [
                    (name, (VENDORED / name).read_text(encoding="utf-8"))
                    for name in VENDORED_LICENSES[key]
                ]
        texts += list(embedded_notices(dist))
        texts += [
            (name, (VENDORED / name).read_text(encoding="utf-8"))
            for name in VENDORED_EXTRA.get(key, ())
        ]
        sections.append(f"\n{'=' * 78}\n{dist.metadata['Name']} {dist.version}\n")
        if not texts:
            raise RuntimeError(f"No license file found for {dist.metadata['Name']}")
        for file, text in texts:
            sections.append(f"--- {file} ---\n{text}\n")
    lib = f"lib/python{sys.version_info.major}.{sys.version_info.minor}/LICENSE.txt"
    for name in ("LICENSE.txt", "LICENSE", lib):
        path = Path(sys.base_prefix) / name
        if path.is_file():
            sections.append(
                f"\n{'=' * 78}\nPython {sys.version.split()[0]}\n"
                + path.read_text(encoding="utf-8")
            )
            break
    else:
        raise RuntimeError("Python license missing from the build environment")

    (output / "THIRD_PARTY_NOTICES.txt").write_text(
        "\n".join(header + source_lines) + "\n" + "".join(sections), encoding="utf-8"
    )


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "build/windows"))
