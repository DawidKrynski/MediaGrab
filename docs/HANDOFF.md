# MediaGrab maintainer guide

This guide records the behavior and safety constraints to preserve when changing
MediaGrab. Setup and test commands are in [DEVELOPMENT.md](DEVELOPMENT.md).

## Default desktop workflow

1. Read the standard clipboard once, accepting one complete HTTP/HTTPS URL.
2. Notify that MediaGrab started.
3. Inspect and save the downloadable media belonging to the single post.
4. Reveal the completed files together in the platform file manager.
5. If the clipboard has no usable URL, show a compact URL field; Enter starts work.

The tray provides progress and cancellation. Without usable tray notifications,
keep the compact progress window visible. Whole profiles/playlists require
confirmation. The detailed GUI is available through the launcher's **Full window**
action, the input context menu, or `--advanced`. Quick mode auto-saves independently
of the detailed GUI's auto-single preference. Do not add continuous clipboard
monitoring, clipboard-history lookup, or implicit collection downloads.

## Backend selection and errors

- Prefer yt-dlp for Instagram reel/reels/TV videos and gallery-dl for `/p/` posts,
  retaining separate carousel images. Preserve the `curl-cffi` dependency used by
  the Instagram networking path.
- Try an alternative engine only for an unsupported URL, not login, rate-limit,
  or network errors. Do not promise universal website compatibility.
- An empty response accompanied by generic cookie-help text is an `access` error,
  not proof of expired cookies. Keep access, authentication, rate-limit, dependency,
  and unavailable errors distinct. Terminal errors take precedence over warnings.
- Do not log cookies, authenticated metadata, or raw backend stderr. Disable
  inherited engine configuration and persistent authentication caches.
- Browser cookies are never extracted automatically. An explicitly selected
  Netscape cookies file is copied privately for the job; the original is unchanged.

## File safety

Preserve staging containment and symlink checks, stable media identities, content
verification for duplicates, no-overwrite publication, root locking, cancellation
of downloader/FFmpeg process groups, and successful items from partial batches.
Completed paths must come from structured backend events. Reinspect stale or
reordered selections instead of weakening identity checks.

Linux file reveal uses FileManager1 `ShowItems` with absolute encoded URIs in one
batch. Windows uses `SHOpenFolderAndSelectItems`, grouping selected files per
folder. If selection fails, open containing folders and report the fallback.
Acceptance of a request alone does not prove visible selection. Initialize COM
on the calling worker thread and release all allocated PIDLs.

Before copying cookies on Windows, restrict the still-empty temporary directory
to the current user's SID. Refuse the operation if ACL setup fails; POSIX mode bits
do not establish Windows privacy. `privacy.py` owns this platform-specific step.

Preferences use Qt QSettings. The default destination is
`~/Downloads/Media/<source>/`; the selected download root holds the duplicate
index. See [the user guide](USAGE.md#files-duplicates-and-cancellation) for storage
semantics and filesystem requirements.

## Implementation map

Modules are under `src/mediagrab/`:

| Module | Responsibility |
| --- | --- |
| `models.py` | Shared items, inspection/results/errors, selection helpers |
| `routing.py`, `backends.py` | URL validation, routing, subprocess adapters |
| `process.py` | Bounded structured output and process-group cancellation |
| `service.py`, `storage.py` | Batch orchestration, staging, duplicate index, publication |
| `reveal.py` | Native Windows/Linux file selection and folder fallback |
| `privacy.py` | Private cookie-directory permissions before copying |
| `gui.py` | Detailed PySide6 window, background worker, preferences, previews |
| `quick.py` | Clipboard launcher, automatic saving, notifications, cancellation |
| `preferences.py` | Shared destination defaults, including empty saved preferences |

Ordinary tests must mock external access. Real-engine integration tests use local
HTTP fixtures only. Separate automated results from native desktop observations
in [VERIFICATION.md](VERIFICATION.md). A widget screenshot demonstrates layout,
not successful real-site downloading or compositor behavior.
