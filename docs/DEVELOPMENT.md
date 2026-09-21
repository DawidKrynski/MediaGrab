# Installation and development

## System requirements

MediaGrab targets Linux and Windows. Python 3.11+ and FFmpeg/ffprobe are needed.
Linux additionally needs a session D-Bus and the Qt runtime libraries required by
your desktop. The Python installation supplies PySide6, yt-dlp, and gallery-dl;
dbus-next is installed only on Linux. Windows verification is tracked in
[VERIFICATION.md](VERIFICATION.md).
YouTube extraction can also require Node.js; use a version supported by the
[installed yt-dlp release](https://github.com/yt-dlp/yt-dlp/wiki/EJS).

Typical system packages on Arch Linux:

```bash
sudo pacman -S --needed python python-pip ffmpeg nodejs xdg-utils
```

On a recent Debian or Ubuntu release:

```bash
sudo apt install python3 python3-venv ffmpeg nodejs xdg-utils
```

These commands install prerequisites; they do not establish compatibility with
every release of those distributions. Check that Python is at least 3.11 and
that Node satisfies yt-dlp's requirements. Qt may need additional distribution
packages for Wayland or X11; see [Qt's installation guide](https://doc.qt.io/qtforpython-6/gettingstarted.html)
and the [troubleshooting guide](USAGE.md#troubleshooting).

## Linux source installation

From the repository's root directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
./scripts/install-desktop.sh
```

The installer creates a desktop menu entry for the current user. It launches
`launch.sh` from this checkout, which uses `.venv/bin/mediagrab`; keep the directory
in place and rerun the installer if you move it. The desktop entry also provides
**Full window**. Normal launches use the compact clipboard workflow.

The package also exposes `mediagrab` and `python -m mediagrab` in its installed
Python environment. To open the detailed interface directly:

```bash
./launch.sh --advanced
```

## Windows source installation

Install [Python 3.11 or newer](https://www.python.org/downloads/windows/),
[FFmpeg/ffprobe](https://ffmpeg.org/download.html#build-windows), and, for YouTube,
a [Node.js](https://nodejs.org/en/download) version supported by yt-dlp. Make
FFmpeg/ffprobe and Node available on PATH. These are separately installed programs;
MediaGrab does not redistribute their binaries. Use an NTFS download destination.

Download or clone the source into a permanent directory and double-click
**Install-Windows.cmd**. The installer checks prerequisites, creates `.venv`,
installs the package and its Python dependencies, then adds **MediaGrab** and
**MediaGrab - Full window** to your Start menu. It changes no system execution
policy; its PowerShell setting applies only to that installer process.

Normal use is graphical: copy a link and open **MediaGrab**. The shortcuts use
`pythonw.exe`, so no terminal remains open. `launch-windows.pyw` is also available
for installations with Python's `.pyw` file association. Keep the checkout in
place because the shortcuts use its environment.

After updating source, rerun **Install-Windows.cmd**. To remove the application,
delete its two Start menu shortcuts and its checkout/virtual environment when
no longer needed. Your downloaded media remains untouched. Windows preferences
use Qt QSettings in `HKEY_CURRENT_USER\Software\MediaGrab\MediaGrab`.

For development in PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m pytest -q --integration
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\python.exe -m pip check
```

Source and an application-only Python wheel are the current distribution scope.
There is no bundled Windows EXE or dependency archive; those would need a separate
[license review](LICENSING.md#bundled-distributions-require-another-review).

## Linux updating and removal

After updating source code, reinstall it in the same environment:

```bash
.venv/bin/python -m pip install --upgrade .
./scripts/install-desktop.sh
```

A non-editable installation does not automatically pick up source changes.
Website support depends on the installed engine versions; after upgrading
engines, rerun the tests below before reporting a verified combination.
`requirements-linux-tested.txt` records the Python environment tested on 2026-09-21,
including test tools. It is a verification snapshot, not a cross-platform lockfile
or a promise that old engines still handle current websites.

To uninstall, remove the **MediaGrab** desktop entry from your user applications
directory (`${XDG_DATA_HOME:-~/.local/share}/applications/mediagrab.desktop`) and
remove this checkout and its virtual environment when no longer needed. Saved
media remains in the download destination. Preferences normally live in
`~/.config/MediaGrab/MediaGrab.conf`; deleting them resets preferences without
removing downloads. The `.mediagrab.sqlite3` file in each download root contains
duplicate records; deleting it causes subsequent downloads to lose that history.

## Development and tests

Use an editable installation while changing code:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q --integration
.venv/bin/ruff check .
.venv/bin/python -m pip check
```

Ordinary tests mock external network access. Opt-in integration tests exercise
real yt-dlp, gallery-dl, and FFmpeg against small generated media served only on
`127.0.0.1`. They require the system tools above. Offscreen Qt tests validate
application behavior but do not establish Wayland clipboard access, notification
delivery, or visible file-manager selection. See [verification](VERIFICATION.md).
Install `desktop-file-utils` to run the desktop-entry validation regression;
that test is skipped when its validator is unavailable.

For packaging checks, build a wheel from a clean source tree, install it into a
new virtual environment, and exercise it from outside the source directory.
This catches accidental dependence on checkout files or an editable install.

## Contributing

Keep ordinary use graphical, with the compact clipboard launcher as the default.
Before changing adapters or file handling, read [the maintainer guide](HANDOFF.md)
and [backend contracts](API_CONTRACTS.md). Test fixes with synthetic inputs and
local fixtures. Include the behavior changed, how it was reproduced, and the
checks performed in a proposed change.

When reporting failures, include MediaGrab/engine versions, desktop environment,
error category, and safe reproduction steps. Never attach a cookies file, browser
profile, private media URL, authentication headers, or unredacted engine output.
Remove personal paths from screenshots. License provenance is tracked separately
in [LICENSING.md](LICENSING.md); contributors must be entitled to contribute code
and identify its source and license when adapting existing work.
