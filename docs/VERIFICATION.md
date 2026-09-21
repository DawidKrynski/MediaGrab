# Verification

MediaGrab separates automated application checks from native desktop observations
and live website compatibility. A passing local download test does not establish
access to an external website.

## Linux regression check after Windows changes — 2026-09-21

The final source suite and a fresh non-editable wheel installation each passed
**120 tests with 3 Windows-only checks skipped**, including all five real-engine
loopback tests. The wheel suite ran outside the source checkout and completed in
11.51 seconds. These results check that the Windows changes preserve the Linux
application paths; they do not expand the native desktop or website coverage below.

## Windows source installation and native GUI — 2026-09-21

A fresh, non-editable wheel installation passed **119 tests with 4 Linux-only
checks skipped**, including all five real-engine loopback integration tests.
Tests ran outside the source checkout in a real **Windows 11 VM, build 26200**,
with Python 3.13.15, PySide6 6.11.2, and FFmpeg 9.0.2.

- **Source installer:** created a fresh `.venv`, installed dependencies, generated
  the application icon, and created both Start menu shortcuts successfully.
- **Native full window:** a local image was inspected and downloaded through the
  visible GUI. Saved bytes matched the fixture; repeating the download correctly
  recognized the duplicate.
- **Explorer:** opened the correct destination folder. On the first native reveal,
  no visible selection appeared; a repeated download then visibly selected the
  file and showed `1 item selected` in Explorer's status bar. First-opening
  selection reliability remains unconfirmed.
- **Platform checks:** native cookie-directory ACL inspection, filesystem guards,
  locking, and downloader-child cancellation were exercised by the Windows suite.
  Windows does not install or import the Linux D-Bus dependency.

No real website, browser credentials, or private media were used. The native
full-window test does not establish the Windows clipboard-to-launch path or
multi-file visual selection. API success alone is not proof of highlighting.
Only this Windows 11 configuration has been tested; other Windows versions and
architectures are not established by these results.

## Earlier Linux installation and cleanup — 2026-09-21

Before the Windows changes, the source environment and a new non-editable wheel
installation both passed **88 tests**, including five real-engine loopback integration tests.
The wheel tests ran outside the source checkout, using a new virtual environment
and isolated preferences. The installed module resolved from that environment's
`site-packages`, rather than an editable source path.

| Check | Result |
| --- | --- |
| Source and installed-wheel test suites | 88 passed in each environment |
| Real engines | Local image, video, DASH merge, exact selection, and quick-GUI save/reveal fixtures passed |
| Fresh GUI smoke | Compact and full windows opened and closed with offscreen Qt; packaged icon present |
| Package entry point | Installed `mediagrab` resolves to `mediagrab.gui:main` |
| Install portability | Desktop entry validates with spaces, quotes, dollar signs, backticks, percent signs, and backslashes in the checkout path |
| Dependency and code checks | `pip check`, Ruff, Bash syntax, and whitespace checks passed |

Regressions cover an empty saved destination falling back to the normal Downloads
directory, refusing an empty download root, and avoiding an accidental open of the
working directory. The icon is now package data and `requests` is an explicit
runtime dependency.

Fresh environment: Python 3.14.7, PySide6 6.11.2, yt-dlp 2026.8.19,
gallery-dl 1.32.13, requests 2.34.2, and Ruff 0.16.8. The exact tested Python
dependencies are in [`requirements-linux-tested.txt`](../requirements-linux-tested.txt).
This is a single Linux host verification, not a cross-distribution compatibility
matrix. The new full-window screenshot [`gui-full.png`](gui-full.png) uses
synthetic entries and a neutral destination. No live website downloads, real
credentials, or native clipboard interaction were used in this run.

## Historical baseline — 2026-09-13

The existing development record reports **82 passing tests**, including five
real-engine loopback integration tests, for version 0.1.2. Ruff, `pip check`, and
desktop-entry validation passed. These are historical results, not a fresh run of
the current source tree.

The historical host used Python 3.14.6, PySide6 6.11.2, yt-dlp 2026.08.19,
gallery-dl 1.32.12, FFmpeg n9.0,
Node v26.4.0, and dbus-next 0.2.3.

| Area | Recorded coverage |
| --- | --- |
| Routing and selection | URL validation, exact selection, collection confirmation, linked media, stale/reordered metadata, distinct error categories |
| File handling | Final-path events, staging containment, symlink refusal, collision preservation, hash-verified duplicates, root lock, partial success |
| Cancellation | Downloader and FFmpeg process-group cancellation, completed-file preservation |
| GUI behavior | Preferences, cookie isolation, worker responsiveness, clipboard parsing, compact input, automatic single-post saving, notifications, retry, and cancellation |
| Real-engine local fixtures | Direct image, single video, DASH audio/video merge, exact second-video selection, compact GUI save/reveal flow |
| Native KDE/Wayland smoke | Compact window opened, one generated local image saved, start/finish notifications issued, FileManager1 request accepted |

The native test supplied a local URL without replacing the system clipboard.
Clipboard-to-launch logic used a mocked Qt clipboard. Visual highlighting inside
the file manager was not independently inspected. The compact input screenshot
[`gui-quick.png`](gui-quick.png) is from that historical native smoke test and
contains no downloaded media or user paths.

## Test policy

Ordinary tests mock external network access. Opt-in integration tests bind an HTTP
fixture only to `127.0.0.1`; this server is never part of the application runtime.
Cookie tests use synthetic files, not real credentials. Run the commands in
[DEVELOPMENT.md](DEVELOPMENT.md#development-and-tests) to check a new environment.

## Limits of the evidence

- Download and merge fixtures are small, generated local files. They do not prove
  current YouTube, Instagram, X, TikTok, Reddit, or Facebook compatibility.
- Login, real cookies, rate limits, private media, and site-specific mixed posts
  have not been established by this test suite.
- Offscreen GUI checks cannot confirm Wayland clipboard permissions, notification
  delivery, tray integration, or file-manager highlighting.
- A successful D-Bus call does not prove that a nonconforming file manager selected
  files visually.
- Crash/power-loss recovery, multi-hour downloads, remote filesystems, other Linux
  distributions/desktops, additional Windows configurations, and macOS behavior
  are not established here.
