from dataclasses import dataclass, field
from pathlib import Path


class MediaError(Exception):
    def __init__(self, kind: str, message: str):
        self.kind = kind
        super().__init__(message)


class Cancelled(MediaError):
    def __init__(self):
        super().__init__("cancelled", "Cancelled; unfinished temporary files were removed.")


class CollectionRequired(MediaError):
    def __init__(self):
        super().__init__(
            "collection", "This link may contain a collection. Inspect up to 100 items?"
        )


@dataclass(frozen=True)
class MediaItem:
    key: str
    backend: str
    source: str
    media_id: str
    title: str
    kind: str
    page_url: str
    quality: str = "Best available"
    thumbnail: str = ""
    selector: dict = field(default_factory=dict)
    collection: bool = False


@dataclass
class Inspection:
    items: list[MediaItem]
    warnings: list[str] = field(default_factory=list)
    collection: bool = False


@dataclass
class BatchResult:
    paths: list[Path] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    skipped: int = 0
    cancelled: bool = False


def default_selection(items: list[MediaItem]) -> set[str]:
    return {items[0].key} if len(items) == 1 else set()


def selected_items(items: list[MediaItem], keys: set[str]) -> list[MediaItem]:
    return [item for item in items if item.key in keys]
