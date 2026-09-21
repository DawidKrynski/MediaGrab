import tempfile
import sqlite3
from dataclasses import replace
from pathlib import Path

from .backends import GalleryAdapter, YtDlpAdapter
from .models import BatchResult, Cancelled, CollectionRequired, MediaError, Inspection
from .routing import is_single_url, route, validate_url
from .storage import Store, contained


class MediaService:
    def __init__(self, runner, cookies=""):
        self.runner = runner
        if cookies and not Path(cookies).expanduser().is_file():
            raise MediaError("cookies", "The explicitly selected cookies file does not exist.")
        # Engines may update cookie jars. Operate only on a private, disposable copy,
        # leaving the user's supplied file untouched. Created by each GUI worker.
        self.adapters = {
            "gallery": GalleryAdapter(runner, cookies),
            "ytdlp": YtDlpAdapter(runner, cookies),
        }

    def inspect(self, url, allow_collection=False, _depth=0):
        url = validate_url(url)
        if not is_single_url(url) and not allow_collection:
            raise CollectionRequired()
        primary, fallback = route(url)
        try:
            result = self.adapters[primary].inspect(url, allow_collection)
        except MediaError as error:
            # Authentication/rate limits are not a reason to hammer the site with another engine.
            if error.kind != "unsupported":
                raise
            result = self.adapters[fallback].inspect(url, allow_collection)
            result.warnings.insert(0, f"{primary} did not support this URL; using {fallback}.")
            if primary == "gallery":
                result.warnings.append(
                    "Video/audio fallback may not expose images from this post. Verify its contents before downloading."
                )
        expanded = []
        for entry in result.items:
            if entry.backend == "queued" and is_single_url(entry.page_url) and _depth < 3:
                try:
                    nested = self.inspect(entry.page_url, False, _depth + 1)
                    expanded.extend(replace(child, source=entry.source) for child in nested.items)
                    result.warnings.extend(nested.warnings)
                    continue
                except Cancelled:
                    raise
                except MediaError as error:
                    result.warnings.append(
                        f"Linked media could not be inspected: [{error.kind}] {error}"
                    )
            elif entry.backend == "queued":
                result.warnings.append(
                    "A linked entry needs separate inspection. Its URL is in the row tooltip; no collection will be downloaded implicitly."
                )
            expanded.append(entry)
        if len(expanded) > 100:
            result.warnings.append("Preview is limited to 100 entries including linked media.")
        return Inspection(
            list({item.key: item for item in expanded[:100]}.values()),
            result.warnings,
            result.collection,
        )

    def download(self, items, root, progress=lambda *_: None, allow_collection=False):
        if not str(root).strip():
            raise MediaError("path", "Choose a destination before downloading.")
        result = BatchResult()
        store = Store(Path(root), self.runner.check)
        try:
            for index, item in enumerate(items):
                try:
                    self.runner.check()
                    progress(index, len(items), item.title, -1)
                    if item.collection and not allow_collection:
                        raise CollectionRequired()
                    existing = store.existing(item.key)
                    if existing:
                        result.paths.append(existing)
                        result.skipped += 1
                        continue
                    if item.backend == "queued":
                        nested = self.inspect(item.page_url, allow_collection=False)
                        if len(nested.items) != 1 or nested.items[0].backend == "queued":
                            raise MediaError(
                                "collection",
                                "Linked entry contains multiple items; paste its URL to inspect and select them.",
                            )
                        item = replace(nested.items[0], source=item.source)
                        existing = store.existing(item.key)
                        if existing:
                            result.paths.append(existing)
                            result.skipped += 1
                            continue
                    with tempfile.TemporaryDirectory(
                        prefix=".mediagrab-work-", dir=store.root
                    ) as temporary:
                        stage = contained(store.root, Path(temporary))
                        path = self.adapters[item.backend].download(
                            item,
                            stage,
                            lambda percent, index=index, title=item.title: progress(
                                index, len(items), title, percent
                            ),
                        )
                        self.runner.check()
                        result.paths.append(store.publish(item, path, stage))
                except Cancelled:
                    result.cancelled = True
                    break
                except MediaError as error:
                    result.failures.append(f"{item.title}: [{error.kind}] {error}")
                except (OSError, sqlite3.Error):
                    result.failures.append(
                        f"{item.title}: File operation failed; check destination permissions and free space."
                    )
        finally:
            store.close()
        return result
