import hashlib
import os
import re
import sqlite3
import stat
import unicodedata
from pathlib import Path

from .models import MediaError


def windows_path_name(value: str) -> str:
    """Compare normal and extended Win32 paths without changing UNC ownership."""
    value = value.replace("/", "\\")
    if value[:8].upper() == "\\\\?\\UNC\\":
        return "\\\\" + value[8:]
    if value.startswith("\\\\?\\"):
        value = value[4:]
        if re.match(r"^[a-zA-Z]:\\", value):
            return value
        raise MediaError("path", "Windows device namespace output paths are refused.")
    if value.startswith("\\\\.\\"):
        raise MediaError("path", "Windows device namespace output paths are refused.")
    return value


def native_path(path: Path) -> Path:
    return Path(windows_path_name(str(path))) if os.name == "nt" else Path(path)


def safe_component(value: str, limit=100) -> str:
    value = unicodedata.normalize("NFKC", str(value))
    value = "".join(c if c.isalnum() or c in " -_.()" else "_" for c in value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    value = value.encode("utf-8")[:limit].decode("utf-8", "ignore").rstrip(" .") or "media"
    # Windows reserves these names even with a file extension. Keep output portable
    # when a download directory later moves between operating systems.
    if re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]", value.split(".")[0], re.I):
        value = "_" + value
    return value.encode("utf-8")[:limit].decode("utf-8", "ignore")


def is_link_or_reparse_point(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & 0x400  # FILE_ATTRIBUTE_REPARSE_POINT
    )


def contained(root: Path, path: Path) -> Path:
    root = native_path(root).resolve()
    path = native_path(path)
    resolved = path.resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise MediaError("path", "Unsafe output path refused.")
    # Do not follow links/junctions even when they currently point inside the root.
    current = path.absolute()
    while current != root and current != current.parent:
        if is_link_or_reparse_point(current):
            raise MediaError("path", "Symlink and reparse-point output paths are refused.")
        current = current.parent
    return resolved


def digest(path: Path, check=lambda: None) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(1024 * 1024):
            check()
            h.update(block)
    return h.hexdigest()


class Store:
    def __init__(self, root: Path, check=lambda: None):
        self.root = native_path(root.expanduser()).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.check = check
        lockpath = contained(self.root, self.root / ".mediagrab.lock")
        if os.name == "nt":
            from ._windows import FileLock

            self.lock = FileLock(lockpath)
        else:
            import fcntl

            self.lock = os.fdopen(
                os.open(lockpath, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), "a"
            )
            try:
                fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                self.lock.close()
                raise MediaError(
                    "busy", "Another MediaGrab download is using this destination."
                ) from None
        try:
            dbpath = contained(self.root, self.root / ".mediagrab.sqlite3")
            self.db = sqlite3.connect(dbpath)
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS files (key TEXT PRIMARY KEY, path TEXT, size INTEGER, hash TEXT)"
            )
        except Exception:
            self.lock.close()
            raise

    def close(self):
        self.db.close()
        self.lock.close()

    def existing(self, key: str) -> Path | None:
        row = self.db.execute("SELECT path,size,hash FROM files WHERE key=?", (key,)).fetchone()
        if row:
            path = contained(self.root, self.root / row[0])
            if (
                path.is_file()
                and path.stat().st_size == row[1]
                and digest(path, self.check) == row[2]
            ):
                return path
        return None

    def publish(self, item, staged: Path, stage_root: Path) -> Path:
        staged = contained(stage_root, staged)
        if not staged.is_file() or staged.stat().st_size == 0:
            raise MediaError("output", "The engine did not produce a completed media file.")
        folder = contained(self.root, self.root / safe_component(item.source, 64))
        folder.mkdir(exist_ok=True)
        ext = safe_component(staged.suffix.lstrip("."), 12)
        if ext in {"part", "ytdl", "tmp"}:
            raise MediaError("output", "The engine reported an unfinished output file.")
        suffix = hashlib.sha256(item.key.encode()).hexdigest()[:12]
        stem = f"{safe_component(item.title)} [{safe_component(item.media_id, 40)}-{suffix}]"
        checksum = digest(staged, self.check)
        self.check()
        for index in range(10000):
            extra = f" ({index})" if index else ""
            target = contained(self.root, folder / f"{stem}{extra}.{ext}")
            try:
                # Atomic, exclusive publication on the same filesystem. Never replace.
                os.link(staged, target, follow_symlinks=False)
                break
            except FileExistsError:
                continue
        else:
            raise MediaError("path", "Too many filename collisions.")
        self.db.execute(
            "INSERT OR REPLACE INTO files VALUES (?,?,?,?)",
            (item.key, str(target.relative_to(self.root)), target.stat().st_size, checksum),
        )
        self.db.commit()
        return target
