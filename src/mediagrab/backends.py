"""Documented CLI adapters. Metadata and final paths use JSON, never console filenames."""

import hashlib
import json
import shutil
from pathlib import Path

from .models import CollectionRequired, Inspection, MediaError, MediaItem
from .process import classify_error
from .routing import is_single_url, source_name
from .runtime import engine_command

MAX_ITEMS = 100


def json_output(output):
    if output.returncode:
        raise classify_error(output.stderr)
    try:
        return json.loads(output.stdout)
    except (ValueError, TypeError):
        raise MediaError(
            "protocol", "The engine returned invalid metadata. Update the application/engine."
        ) from None


def final_paths(output) -> list[Path]:
    paths = []
    for line in output.stdout.splitlines():
        if line.startswith("MGFILE:"):
            try:
                value = json.loads(line[7:])
                if isinstance(value, str) and Path(value).is_absolute():
                    paths.append(Path(value))
            except ValueError:
                pass
    if output.returncode:
        raise classify_error(output.stderr)
    if len(paths) != 1:
        raise MediaError(
            "selection", "Expected exactly one completed selected item; nothing was published."
        )
    return paths


def quality(meta):
    width = meta.get("width") or meta.get("image_width")
    height = meta.get("height") or meta.get("image_height")
    parts = [f"{width or '?'} × {height}" if height else "Best available"]
    if meta.get("duration"):
        parts.append(f"{meta['duration']} s")
    return " · ".join(parts)


class YtDlpAdapter:
    name = "ytdlp"

    def __init__(self, runner, cookies=""):
        self.runner, self.cookies = runner, cookies

    def base(self):
        args = [
            *engine_command("yt_dlp"),
            "--ignore-config",
            "--no-colors",
            "--no-playlist",
            "--socket-timeout",
            "20",
            "--retries",
            "2",
            "--extractor-retries",
            "2",
            "--no-cache-dir",
        ]
        if shutil.which("node"):
            args += ["--js-runtimes", "node"]
        if self.cookies:
            args += ["--cookies", self.cookies]
        return args

    def inspect(self, url, allow_collection=False):
        data = json_output(
            self.runner.run(
                self.base()
                + [
                    "--dump-single-json",
                    "--skip-download",
                    "--flat-playlist",
                    "--playlist-items",
                    "1:101",
                    "--",
                    url,
                ]
            )
        )
        if not isinstance(data, dict):
            raise MediaError("protocol", "Unexpected yt-dlp metadata shape.")
        collection = data.get("_type") in {"playlist", "multi_video"} or "entries" in data
        if collection and not is_single_url(url) and not allow_collection:
            raise CollectionRequired()
        entries = data.get("entries", []) if collection else [data]
        items, warnings = [], []
        if len(entries) > MAX_ITEMS or (data.get("playlist_count") or 0) > MAX_ITEMS:
            warnings.append(
                "Collection preview is limited to the first 100 entries. Use individual links for the rest."
            )
        for index, entry in enumerate(entries[:MAX_ITEMS], 1):
            if not entry or not entry.get("id"):
                warnings.append(f"Entry {index} is unavailable or has no stable identifier.")
                continue
            media_id = str(entry["id"])
            extractor = str(
                entry.get("extractor_key")
                or entry.get("ie_key")
                or data.get("extractor_key")
                or "generic"
            )
            item_url = entry.get("webpage_url") or entry.get("url") or url
            if not isinstance(item_url, str) or not item_url.startswith(("https://", "http://")):
                item_url = url
            # Parent plus index and an ID filter is safe even when entries reorder.
            selector = (
                {"id": media_id, "index": entry.get("playlist_index") or index}
                if collection
                else {"id": media_id}
            )
            page = url if collection else item_url
            thumbnail = entry.get("thumbnail") or next(
                (t["url"] for t in reversed(entry.get("thumbnails") or []) if t.get("url")), ""
            )
            kind = "audio" if entry.get("vcodec") == "none" else "video"
            namespace = source_name(url)
            if extractor.lower() == "generic":
                namespace += ":" + hashlib.sha256(url.encode()).hexdigest()[:20]
            items.append(
                MediaItem(
                    f"yt:{namespace}:{extractor.lower()}:{media_id}",
                    self.name,
                    source_name(url),
                    media_id,
                    entry.get("title") or media_id,
                    kind,
                    page,
                    quality(entry),
                    thumbnail,
                    selector,
                    collection,
                )
            )
        if not items:
            raise MediaError("unavailable", "No downloadable video/audio entries were found.")
        return Inspection(items, warnings, collection)

    def download(self, item, stage, progress):
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            raise MediaError(
                "dependency",
                "FFmpeg and ffprobe are required for best-quality video/audio merging.",
            )
        args = self.base() + [
            "--no-simulate",
            "--no-overwrites",
            "--no-continue",
            "--format",
            "bv*+ba/b",
            "--paths",
            str(stage),
            "--output",
            "media.%(ext)s",
            "--restrict-filenames",
            "--print",
            "after_move:MGFILE:%(filepath)j",
            "--newline",
            "--progress",
            "--progress-delta",
            "0.25",
            "--progress-template",
            "download:MGPROGRESS:%(progress)j",
            "--match-filters",
            "id = " + json.dumps(item.selector["id"]),
        ]
        if "index" in item.selector:
            args += ["--playlist-items", str(item.selector["index"])]
        else:
            # Defensive bound against a formerly single URL becoming a collection.
            args += ["--playlist-items", "1"]

        def line_received(line):
            if line.startswith("MGPROGRESS:"):
                try:
                    data = json.loads(line[11:])
                    total = data.get("total_bytes") or data.get("total_bytes_estimate")
                    done = data.get("downloaded_bytes", 0)
                    progress(min(100, int(done * 100 / total)) if total else -1)
                except (ValueError, TypeError):
                    pass

        return final_paths(
            self.runner.run(args + ["--", item.page_url], timeout=86400, on_line=line_received)
        )[0]


# Stable, scalar extractor metadata, independent of temporary CDN query strings.
IDENTITY_FIELDS = (
    "category",
    "subcategory",
    "id",
    "post_id",
    "tweet_id",
    "media_id",
    "shortcode",
    "code",
    "file_id",
    "filename",
    "num",
    "offset",
    "type",
    "extension",
    "domain",
    "path",
)


def gallery_identity(meta):
    return {
        key: meta[key]
        for key in IDENTITY_FIELDS
        if key in meta and isinstance(meta[key], (str, int, bool)) and len(str(meta[key])) <= 300
    }


class GalleryAdapter:
    name = "gallery"

    def __init__(self, runner, cookies=""):
        self.runner, self.cookies = runner, cookies

    def base(self):
        args = [
            *engine_command("gallery_dl"),
            "--config-ignore",
            "--no-input",
            "--no-colors",
            "--retries",
            "2",
            "--http-timeout",
            "20",
            "-o",
            "cache.file=null",
            "--range",
            "1-101",
            "--child-range",
            "1-101",
            "-o",
            "extractor.facebook.videos=ytdl",
            "-o",
            "extractor.reddit.videos=ytdl",
            "-o",
            "extractor.tiktok.videos=ytdl",
            "-o",
            "extractor.twitter.retweets=false",
            "-o",
            "extractor.twitter.quoted=false",
            "-o",
            "extractor.reddit.comments=0",
            "-o",
            "downloader.ytdl.module=yt_dlp",
            "-o",
            'downloader.ytdl.raw-options={"noplaylist":true,"quiet":true,"nocheckcertificate":false}',
            "-o",
            "extractor.cookies-update=false",
        ]
        if self.cookies:
            args += ["--cookies", self.cookies]
        return args

    def inspect(self, url, allow_collection=False):
        if not is_single_url(url) and not allow_collection:
            raise CollectionRequired()
        rows = json_output(self.runner.run(self.base() + ["--dump-json", "--", url]))
        if not isinstance(rows, list):
            raise MediaError("protocol", "Unexpected gallery-dl metadata shape.")
        items, warnings = [], []
        for row in rows:
            if not isinstance(row, list) or not row:
                raise MediaError("protocol", "Unexpected gallery-dl message shape.")
            if row[0] == -1:
                error = classify_error(str(row[-1]))
                if not items:
                    raise error
                warnings.append(str(error))
            elif row[0] in (3, 6):
                media_url, meta = row[1], row[-1]
                if row[0] == 6:
                    # Surface queued entries explicitly; never silently discard a mixed post's video.
                    identity = hashlib.sha256(media_url.encode()).hexdigest()[:20]
                    items.append(
                        MediaItem(
                            f"queue:{identity}",
                            "queued",
                            source_name(url),
                            identity,
                            meta.get("title") or "Linked media (inspected before download)",
                            "linked media",
                            media_url,
                            "Requires inspection",
                            collection=True,
                        )
                    )
                    continue
                identity = gallery_identity(meta)
                if not any(
                    k in identity
                    for k in ("id", "post_id", "tweet_id", "media_id", "filename", "file_id")
                ):
                    warnings.append(
                        "An entry had no stable identity and cannot safely be downloaded."
                    )
                    continue
                serialized = json.dumps(identity, sort_keys=True)
                stable_id = str(
                    meta.get("media_id")
                    or meta.get("id")
                    or meta.get("tweet_id")
                    or meta.get("filename")
                )
                key = (
                    f"gallery:{source_name(url)}:" + hashlib.sha256(serialized.encode()).hexdigest()
                )
                ext = str(meta.get("extension", "")).lower()
                kind = (
                    "video"
                    if ext in {"mp4", "webm", "mov", "mkv", "m3u8", "mpd"}
                    or media_url.startswith("ytdl:")
                    else "audio"
                    if ext in {"mp3", "m4a", "ogg", "opus", "wav"}
                    else "image"
                )
                thumbnail = meta.get("thumbnail") or meta.get("thumbnail_url") or ""
                if not isinstance(thumbnail, str):
                    thumbnail = ""
                items.append(
                    MediaItem(
                        key,
                        self.name,
                        source_name(url),
                        stable_id,
                        str(
                            meta.get("title")
                            or meta.get("description")
                            or meta.get("content")
                            or meta.get("filename")
                            or stable_id
                        )[:500],
                        kind,
                        url,
                        quality(meta),
                        thumbnail,
                        identity,
                        not is_single_url(url),
                    )
                )
        if len(items) > MAX_ITEMS:
            warnings.append(
                "Only the first 100 media entries are shown. Use individual links for additional entries."
            )
        # Deduplicate engine results without collapsing separate image/video variants.
        items = list({item.key: item for item in items[:MAX_ITEMS]}.values())
        if not items:
            raise MediaError("unsupported", "gallery-dl found no supported media at this URL.")
        return Inspection(items, warnings, not is_single_url(url))

    def download(self, item, stage, progress):
        fresh = self.inspect(item.page_url, allow_collection=True)
        matches = [candidate for candidate in fresh.items if candidate.key == item.key]
        if len(matches) != 1:
            raise MediaError(
                "expired", "The selected entry changed or disappeared. Inspect the link again."
            )
        if item.kind == "video" and not shutil.which("ffmpeg"):
            raise MediaError("dependency", "FFmpeg is required to download and merge this video.")
        # Match stable metadata again during the fresh download extraction, never an ordinal alone.
        expr = " and ".join(f"{key} == {value!r}" for key, value in item.selector.items())
        args = self.base() + [
            "--directory",
            str(stage),
            "--filename",
            "media.{extension}",
            "--restrict-filenames",
            "ascii",
            "--filter",
            expr,
            "--child-filter",
            "False",
            "--Print",
            "after:MGFILE:{_path.realpath!j}",
            "--",
            item.page_url,
        ]
        progress(-1)
        return final_paths(self.runner.run(args, timeout=86400))[0]
