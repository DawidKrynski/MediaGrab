# Backend integration contracts

These contracts were recorded against the 2026-09-13 dependency baseline. They
describe the interfaces MediaGrab uses, not permanent website compatibility.
See [verification](VERIFICATION.md) for executed tests and current limits.

## yt-dlp 2026.08.19

[Official README / CLI options](https://github.com/yt-dlp/yt-dlp#usage-and-options)
and [output templates](https://github.com/yt-dlp/yt-dlp#output-template):

- `--dump-single-json --skip-download --flat-playlist` returns inspection metadata.
- `--no-playlist` targets a video when its URL also refers to a playlist. It alone
  is not a safety guard for a playlist-only URL; the application adds confirmation,
  bounded `--playlist-items`, and selection checks.
- `--match-filters` compares the selected `id`; `--playlist-items` bounds the index.
- `--format bv*+ba/b` selects video and audio with a combined-format fallback.
- `--print after_move:MGFILE:%(filepath)j` gives the JSON-encoded final path after
  processing; `--no-simulate` ensures printing does not suppress download.
- `--progress-template download:MGPROGRESS:%(progress)j` supplies structured progress.
- `--cookies FILE`, `--ignore-config`, `--no-cache-dir`, and Node `--js-runtimes`
  are verified CLI options. No browser cookies are requested.

The package's default extra supplies EJS. See [official extractor notes](https://github.com/yt-dlp/yt-dlp/wiki/Extractors)
for website-specific restrictions and token limitations. Local real-engine tests
verify ID-filter syntax, final paths, DASH merging, and playlist selection.

## gallery-dl 1.32.12

[Official CLI options](https://github.com/mikf/gallery-dl/blob/master/docs/options.md),
[configuration](https://github.com/mikf/gallery-dl/blob/master/docs/configuration.rst),
and [extractor message definitions](https://github.com/mikf/gallery-dl/blob/master/gallery_dl/extractor/message.py):

- `--dump-json` produces message arrays: Directory = 2, media URL = 3, queued
  extractor URL = 6. Metadata is the last element. Both two- and three-element
  directory records are tolerated because directory messages are not media rows.
- `DataJob` in [job.py](https://github.com/mikf/gallery-dl/blob/master/gallery_dl/job.py)
  can emit `[-1, error metadata]` even with exit code zero. Those errors are checked.
- `--filter` applies an expression over scalar metadata; only a fixed allowlist
  of field names and Python-quoted scalar values enters the expression.
- `--directory` selects the exact directory; `--filename media.{extension}` limits
  the template; `--child-filter False` prevents downloads of queued child extractors.
- `--Print after:MGFILE:{_path.realpath!j}` prints the completed path. Capitalized
  `--Print` retains downloading. The `after` event runs after the file is moved;
  `!j` JSON-encodes the path. Verified against installed formatter/metadata/path
  implementations and a real loopback image download.
- `--range` and `--child-range` bound extraction. `--config-ignore --no-input`,
  `cache.file=null`, and explicit `--cookies FILE` isolate configuration/authentication.
- Configured video delegation for Reddit/Facebook/TikTok uses documented `videos=ytdl`;
  `downloader.ytdl.raw-options` disables playlist expansion and sets quiet output.

Gallery download percentage is not scraped from console text; the GUI displays
indeterminate per-file progress plus a batch counter.

## Linux file selection

The [FileManager1 specification](https://www.freedesktop.org/wiki/Specifications/file-manager-interface/)
was corroborated against the [GNOME interface discussion](https://bugzilla.gnome.org/show_bug.cgi?id=636269)
and session introspection in the historical KDE smoke test:

- Bus destination/interface: `org.freedesktop.FileManager1`.
- Object path: `/org/freedesktop/FileManager1`; method: `ShowItems`.
- Signature: `ass`; arguments: array of absolute encoded file URIs, then startup ID.

`pathlib.Path.as_uri()` supplies the encoding. `dbus-next` sends a correctly typed
array, avoiding ambiguous Python-list QVariant marshalling. One request carries
all completed paths. Failure opens each distinct containing directory once and
reports that selection was unavailable. An accepted call is not proof that every
file manager implements selection correctly.

## Instagram routing and error classification

Reel/reels/TV single-video URLs now use yt-dlp first; `/p/` posts continue to use
gallery-dl to preserve carousel images. The official
[yt-dlp impersonation dependency](https://github.com/yt-dlp/yt-dlp#impersonation)
`curl-cffi` is installed through the documented extra. No browser profile is read.

An empty-media response containing general cookie-help text is classified as
`access`, not as an affirmative authentication/expired-cookie error. Rate-limit
errors and definite authentication errors retain distinct categories. CLI terminal
errors take precedence over earlier warning lines.

## Clipboard launcher

[QClipboard.text()](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QClipboard.html)
reads the standard clipboard once after showing a surface for Wayland clipboard
access. Unrelated text is discarded; no clipboard history is read or persisted.
[QSystemTrayIcon](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QSystemTrayIcon.html)
provides startup/completion notifications with `showMessage`, and a context menu
with progress/cancellation. Missing tray/notification support leaves a compact
progress dialog visible. The existing Worker performs metadata and download work
off the GUI thread; quick inspection skips unnecessary thumbnail requests.


## Windows file selection and cookie privacy

[SHOpenFolderAndSelectItems](https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-shopenfolderandselectitems)
opens Explorer with a per-folder array of selected items. MediaGrab initializes
COM on the worker thread, resolves absolute paths with
[SHParseDisplayName](https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-shparsedisplayname),
and obtains relative child pointers with
[ILFindLastID](https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-ilfindlastid).
Allocated parent/full item lists remain alive until selection completes and are
released with `CoTaskMemFree`; child pointers are not separately freed. The folder
fallback uses `os.startfile`, invoking the registered Windows shell handler.

Before authentication files are copied, the empty private directory receives a
protected ACL allowing the current user SID full control. Windows `whoami` obtains
the SID and `icacls` replaces inherited/default rules. Both run without a shell or
console, with captured output that is never logged. Failure prevents copying any
cookies. The native Windows privacy test inspects the resulting ACL separately.
