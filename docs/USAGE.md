# MediaGrab user guide

See the [README](../README.md) for the everyday clipboard workflow and installation.

## Full window (optional)

Open the desktop launcher’s **Full window** action; developers can use
`./launch.sh --advanced`.

1. Paste a media URL and press Enter or **Inspect**. Extraction reads metadata,
   not full media. Small explicit thumbnails are fetched when available.
2. One result is checked automatically. Multiple results start unchecked; use
   individual checkboxes or **Select all**.
3. Change the download root if desired. Site folders are added automatically:
   `youtube`, `instagram`, `x`, `tiktok`, `reddit`, `facebook`; other hosts get a
   sanitized hostname. Public content may still be restricted by the website.
4. Optionally choose an explicit Netscape-format cookies file for login-only
   content. The app uses a private, disposable copy, never the browser profile,
   and never logs cookies or raw engine errors. The original file is not modified.
5. Click **Download selected**. Best available video plus audio is the default;
   FFmpeg merges streams without intentional re-encoding. Progress is per item
   with a batch counter; gallery-dl transfers use an indeterminate progress bar.
6. **Cancel** stops the downloader process group, including FFmpeg. Completed
   entries remain; this operation's unfinished staging directory is removed.
7. Successful files are revealed together after the batch, including after partial
   failure or cancellation. If native file selection is unavailable, the app
   opens containing folders and explicitly reports the fallback.

**In the full window only**, **Automatically download single items** defaults to off. It never starts a
collection, a linked unresolved entry, or an inspection with warnings automatically.
The app asks before inspecting possible channels, profiles, playlists, unknown
links, and short URLs; it asks separately before downloading collection selections.
A YouTube watch URL with a `list` parameter targets only that video. Collection
inspection is capped at 100 entries, with a notice when more are discovered.

**Open folder** opens the configured root. It is intentionally separate from the
automatic completed-file selection behavior.

## Site support and limits

Support depends on the installed engines and the website's current access rules.
This is not a universal downloader, and no access restrictions are bypassed.

| Input | Preferred engine | Notes |
| --- | --- | --- |
| YouTube video/short/live or explicit playlist selection | yt-dlp | FFmpeg for separate streams; Node/EJS for challenges. Live streams can be long-running; Cancel is available. |
| Instagram post / carousel | gallery-dl | Images and videos stay separate selectable entries; access may require an explicitly supplied cookies file. |
| Instagram reel / TV video | yt-dlp | Uses its public-video extraction with the installed networking transport. Anonymous access can still be restricted. |
| X/Twitter status | gallery-dl | Retweets/quoted posts are not recursively expanded. Login/rate limits depend on the site. |
| TikTok photo/video post | gallery-dl | Photos, accompanying audio, and video remain selectable; video extraction can delegate internally to yt-dlp. |
| Reddit post/gallery | gallery-dl | Images and videos, including supported linked single videos. Comment crawling is disabled. |
| Facebook video | yt-dlp | Photo/set/post URLs try gallery-dl; arbitrary mixed Facebook posts are not guaranteed supported. |
| Direct image URL | gallery-dl | No full image download during inspection. |
| Other media pages / direct video or audio URLs | yt-dlp, then gallery-dl on unsupported URL | Unknown pages require collection confirmation. |

The alternative engine is inspected only after an **unsupported** result. Login,
rate limit, and network errors do not trigger blind retries with both engines.
Only the adapter associated with each chosen item downloads it. Video/audio fallback
from a social gallery reports that images may not be exposed; it does not claim a
complete mixed-post inventory.

Embedded known single-media links are inspected into the same selection list.
Unrecognized links, nested collections, and links that fail inspection remain
visible with a warning instead of disappearing. Hover their title for the URL and
paste that link separately to inspect its collection; nested collections never
expand into an implicit download. Metadata resolution has a depth limit of three.

Quality labels use available metadata; flat playlist entries may have incomplete
quality information. Downloads still request the best available formats. There is
no quality picker, video-to-MP3 conversion, DRM support, browser credential lookup,
PO-token configuration, or guarantee of private/account-only access. An ordinary
network/engine error is deliberately reported with a sanitized category rather
than potentially sensitive raw stderr.

Thumbnail requests have an 8-second total budget, a 2 MB per-image limit, and no
cookies. Some rows may therefore have no thumbnail. Original gallery images are
never downloaded just to fabricate previews.

## Files, duplicates, and cancellation

Names contain a sanitized readable title, stable media ID, and short identity hash.
An SQLite index (`.mediagrab.sqlite3`) in the chosen root stores identity, relative
path, size, and SHA-256. A duplicate is skipped only if the recorded file still
exists with matching content. Moving/deleting/modifying it causes a fresh download.
Changing the root creates an independent index.

Downloads run in private `.mediagrab-work-*` directories inside that root. Only
engine-reported completed paths are published. The final publication uses an
exclusive hard link, never a replacing rename; unrelated existing names gain a
numeric suffix. Symlink destinations beneath the root and escaping paths are
refused. The root itself may be an explicitly chosen resolved symlink. Destinations
must support hard links and file locking: use ext4/Btrfs on Linux or NTFS on
Windows. FAT/exFAT and some remote filesystems may reject publication.

Choose a download directory you control. MediaGrab rejects known links in output
paths, but its path checks do not isolate downloads from another process changing
directory links during publication.

The root lock prevents concurrent MediaGrab writers. Failed items do not discard
successful siblings. Download jobs re-extract current metadata: gallery identities
are checked after refresh and filtered again on download; yt-dlp uses an ID filter
plus the selected parent index. A reordered playlist may require reinspection,
rather than silently downloading a different item. Interrupted downloads restart
from scratch. A forced OS kill/power failure can leave a private staging directory;
after confirming no instance is running, it may be removed. Crash leftovers are
never automatically treated as completed files.

Preferences use Qt's `QSettings`: normally `~/.config/MediaGrab/MediaGrab.conf` on
Linux, or `HKEY_CURRENT_USER\Software\MediaGrab\MediaGrab` on Windows.
Only preferences and the explicitly supplied cookies-file **path** are persisted
there. The application does not persist extracted metadata or CDN URLs in its index.
Engine default configuration and persistent authentication caches are disabled.

## Troubleshooting

- **Dependency:** check `ffmpeg -version`, `ffprobe -version`, `node --version`,
  `.venv/bin/python -m yt_dlp --version`, and `.venv/bin/python -m gallery_dl --version`.
  In Windows PowerShell, replace `.venv/bin/python` with `.\.venv\Scripts\python.exe`.
- **Unsupported:** try a canonical single-post URL and update the engines. Short,
  user/profile, search, or redirect URLs may not expose a downloadable entry.
- **Access:** Instagram supplied no media data. The post may be unavailable or
  restricted to anonymous requests; this alone does not establish expired cookies.
- **Login:** if you already have a valid Netscape cookies file, select it using **Choose…**. Account access is not
  created or repaired by this application.
- **Rate limit:** stop and retry later. Repeated engine switching is avoided.
- **Unavailable:** content may be private, deleted, geographically restricted, or
  access denied; cookies cannot guarantee availability.
- **Network / timeout:** check connectivity, update engines, and retry a single URL.
  Inspection times out after 180 seconds per extractor; downloads after 24 hours.
- **Selection changed:** inspect again and choose the current entry. Do not remove
  identity guards to force a stale selection.
- **File selection unavailable:** on Windows, MediaGrab asks Explorer to select
  each folder's completed files together. On Linux, run inside the graphical user's
  D-Bus session.
  A compatible file manager must expose FileManager1; otherwise the folder fallback
  is reported. An accepting but nonconforming file manager cannot be detected remotely.
- **Qt will not launch on Linux:** run from your desktop terminal; install your distribution's
  Qt/Wayland or xcb runtime libraries. `QT_QPA_PLATFORM=xcb ./launch.sh` can help on a
  Wayland session with XWayland installed. Offscreen is for tests, not interactive use.
- **Destination busy / file operation failed:** close the other download, check free
  space, permissions, and filesystem hard-link support. Downloaded files are not
  removed when uninstalling the app or deleting its index.

