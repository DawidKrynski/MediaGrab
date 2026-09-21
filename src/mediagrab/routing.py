import re
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from .models import MediaError

SOURCES = {
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "instagram.com": "instagram",
    "twitter.com": "x",
    "x.com": "x",
    "tiktok.com": "tiktok",
    "tiktokv.com": "tiktok",
    "reddit.com": "reddit",
    "redd.it": "reddit",
    "facebook.com": "facebook",
    "fb.watch": "facebook",
}
GALLERY_SOURCES = {"instagram", "x", "reddit", "tiktok"}


def validate_url(url: str) -> str:
    url = url.strip()
    try:
        p = urlsplit(url)
        valid = p.scheme in {"http", "https"} and p.hostname and not p.username and not p.password
        _ = p.port
    except ValueError:
        valid = False
    if not valid or any(ord(c) < 32 for c in url):
        raise MediaError(
            "unsupported", "Enter an absolute HTTP or HTTPS media URL without credentials."
        )
    # A watch URL with a list parameter still means just the requested video.
    if source_name(url) == "youtube" and parse_qs(p.query).get("v"):
        q = {
            k: v for k, v in parse_qs(p.query).items() if k not in {"list", "index", "start_radio"}
        }
        return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q, doseq=True), ""))
    return url


def source_name(url: str) -> str:
    host = (urlsplit(url).hostname or "unknown").lower()
    for domain, source in SOURCES.items():
        if host == domain or host.endswith("." + domain):
            return source
    return re.sub(r"[^a-z0-9-]", "-", host.removeprefix("www."))[:64] or "unknown"


def route(url: str) -> tuple[str, str]:
    source = source_name(url)
    gallery = source in GALLERY_SOURCES or bool(
        re.search(r"\.(?:jpe?g|png|gif|webp|avif|bmp)$", urlsplit(url).path, re.I)
    )
    # Reels/TV are video URLs. Keep /p/ with gallery-dl so carousels retain images.
    if source == "instagram" and re.fullmatch(r"/(?:reels?|tv)/[^/?#]+/?", urlsplit(url).path):
        gallery = False
    if source == "facebook":
        gallery = bool(
            re.search(r"/(?:photo|photo.php|photos|media/set|posts/)", urlsplit(url).path)
        )
    return ("gallery", "ytdlp") if gallery else ("ytdlp", "gallery")


def is_single_url(url: str) -> bool:
    p = urlsplit(url)
    path = p.path
    source = source_name(url)
    if source == "youtube":
        return bool(
            parse_qs(p.query).get("v")
            or re.match(r"/(shorts|live|embed)/[^/]+", path)
            or (p.hostname == "youtu.be" and path.strip("/"))
        )
    if source == "instagram":
        return bool(re.match(r"/(p|reel|reels|tv)/[^/]+", path))
    if source == "x":
        return bool(re.search(r"/(?:status|statuses)/\d+", path))
    if source == "tiktok":
        return bool(re.search(r"/@[^/]+/(?:video|photo)/\d+", path))
    if source == "reddit":
        return bool(
            re.search(r"/(?:comments|gallery)/[a-zA-Z0-9]+", path)
            or (p.hostname == "redd.it" and path.strip("/"))
        )
    if source == "facebook":
        return bool(
            re.search(r"/(?:videos|reel|posts)/[^/]+", path)
            or parse_qs(p.query).get("v")
            or parse_qs(p.query).get("fbid")
        )
    return bool(
        re.search(
            r"\.(?:jpe?g|png|gif|webp|avif|bmp|mp4|webm|mov|mkv|mp3|m4a|ogg|opus|wav|mpd|m3u8)$",
            path,
            re.I,
        )
    )
    # Other unknown/short URLs get a conservative collection confirmation.
