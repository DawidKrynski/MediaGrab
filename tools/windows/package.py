"""Assemble the portable Windows folder, then write the ZIP and SHA256SUMS.txt.

Usage:
    python tools/windows/package.py assemble <PyInstaller MediaGrab dir> <notices dir> <output>
    python tools/windows/package.py archive <output>
"""

import hashlib
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = "MediaGrab-Windows-x64.zip"


def assemble(frozen, notices, output):
    folder = output / "MediaGrab"
    if folder.exists():
        shutil.rmtree(folder)
    shutil.copytree(frozen, folder)
    shutil.copyfile(ROOT / "LICENSE", folder / "LICENSE.txt")
    shutil.copyfile(notices / "THIRD_PARTY_NOTICES.txt", folder / "THIRD_PARTY_NOTICES.txt")
    shutil.copytree(notices / "sources", folder / "sources")
    shutil.copyfile(Path(__file__).with_name("README.txt"), folder / "README.txt")
    for required in ("MediaGrab.exe", "mediagrab-engine.exe", "_internal"):
        if not (folder / required).exists():
            raise RuntimeError(f"Portable folder is missing {required}")
    check_no_addons(folder)
    notices_text = (folder / "THIRD_PARTY_NOTICES.txt").read_text(encoding="utf-8")
    for marker in ("GNU LESSER GENERAL PUBLIC LICENSE", "Qt third-party attributions",
                   "curl_cffi's libcurl-impersonate", "sources/gallery_dl-", "PYTHON SOFTWARE FOUNDATION LICENSE"):
        if marker.lower() not in notices_text.lower():
            raise RuntimeError(f"THIRD_PARTY_NOTICES.txt lacks {marker!r}")
    return folder


def check_no_addons(folder):
    """The notices treat PySide6 Addons as installed but not shipped; enforce that."""
    try:
        files = distribution("PySide6_Addons").files or ()
    except PackageNotFoundError:
        return
    native = {file.name.lower() for file in files if file.suffix.lower() in {".dll", ".pyd"}}
    shipped = {path.name.lower() for path in folder.rglob("*") if path.is_file()}
    if native & shipped:
        raise RuntimeError(f"PySide6 Addons binaries were bundled: {sorted(native & shipped)}")


def archive(folder, output):
    target = output / ARCHIVE
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                bundle.write(path, Path("MediaGrab") / path.relative_to(folder))
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    (output / "SHA256SUMS.txt").write_text(f"{digest}  {ARCHIVE}\n", encoding="ascii")
    return target, digest


if __name__ == "__main__":
    command, *paths = sys.argv[1:]
    paths = [Path(value).resolve() for value in paths]
    if command == "assemble" and len(paths) == 3:
        paths[2].mkdir(parents=True, exist_ok=True)
        print(assemble(*paths))
    elif command == "archive" and len(paths) == 1:
        target, digest = archive(paths[0] / "MediaGrab", paths[0])
        print(f"{digest}  {target.name}  {target.stat().st_size} bytes")
    else:
        sys.exit(__doc__)
