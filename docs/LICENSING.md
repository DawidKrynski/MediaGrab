# Licensing

Review date: 2026-09-21.

MediaGrab's own source code and assets are covered by the [MIT license](../LICENSE).
Its dependencies retain their respective licenses; MIT does not relicense them.
MediaGrab integrates independently installed downloaders rather than incorporating
their source code.

## Current source distribution

The repository contains the application, its own icon and screenshots, tests, and
documentation. It does not contain downloader sources, dependency wheels, native
libraries, or a bundled Python environment. The application-only Python wheel
also declares dependencies for separate installation.

The review covered declared licenses and available license files for **29 Python
packages**, including runtime dependencies and development tools. The exact
versions and license information are recorded in
[Third-party notices](../THIRD_PARTY_NOTICES.md). This is not a complete audit of
the native libraries inside third-party wheels.

## How the application uses dependencies

MediaGrab launches `python -m yt_dlp` and `python -m gallery_dl` as separate
processes through their documented command-line interfaces. It exchanges ordinary
command arguments, JSON metadata, progress output, and downloaded files. It does
not import these engines into the application or include their implementation.
Any delegation from gallery-dl to yt-dlp happens inside the downloader process.

This interface supports treating MediaGrab's original wrapper code separately
from the engines. Process separation alone is not a blanket GPL exemption: the
[FSF aggregation guidance](https://www.gnu.org/licenses/gpl-faq.en.html#MereAggregation)
also considers what the programs exchange. Review this assessment if engine code
is copied, linked, or integrated through a different interface.

The GUI imports PySide6's QtCore, QtGui, and QtWidgets. These modules offer an
LGPLv3 licensing path: [Qt Core](https://doc.qt.io/qt-6/qtcore-index.html#licenses-and-attributions),
[Qt GUI](https://doc.qt.io/qt-6/qtgui-index.html#licenses-and-attributions), and
[Qt Widgets](https://doc.qt.io/qt-6/qtwidgets-index.html#licenses-and-attributions).
The source installation leaves PySide6 separately installed and replaceable;
MediaGrab adds no restriction on modifying or replacing those libraries.
Requests and dbus-next are also separately installed libraries. FFmpeg/ffprobe
and Node are external programs.

When distributing MediaGrab's own source or application-only wheel, include its
MIT license and keep the dependency notices. Preserve applicable notices and
check compatibility before adding any third-party code or assets to this tree.

## Bundled distributions require another review

A frozen executable, AppImage, container, wheelhouse, or archived virtual
environment can redistribute components absent from this repository. Before
shipping one, inventory its exact contents and supply the applicable license
texts, copyright notices, and any required corresponding source:

- **Qt/PySide6:** satisfy the applicable LGPL/GPL terms, including library
  replacement or relinking and source requirements where applicable. Check
  bundled modules and native components individually; not every Qt module offers
  LGPL. See [Qt licensing](https://doc.qt.io/qt-6/licensing.html),
  [LGPLv3 terms](https://doc.qt.io/qt-6/lgpl.html), and
  [Qt for Python third-party notices](https://doc.qt.io/qtforpython-6/licenses.html).
- **gallery-dl:** GPL-2.0-only. Redistributed copies retain its license and notices;
  binary distribution must satisfy the applicable source requirements. See its
  [license](https://github.com/mikf/gallery-dl/blob/master/LICENSE).
- **yt-dlp:** the PyPI package uses Unlicense, while standalone release executables
  include differently licensed code. See the upstream
  [artifact-specific licensing notes](https://github.com/yt-dlp/yt-dlp#licensing).
- **FFmpeg:** licensing depends on enabled components and the actual build. See
  [FFmpeg's guidance](https://ffmpeg.org/legal.html).
- **Other dependencies:** retain their own notices and applicable source duties,
  including certifi's MPL-2.0 and mutagen's GPL-2.0-or-later terms. Native payloads
  inside curl-cffi and Qt need their own inventory.

Recheck this review whenever dependencies, integration, or packaging change.

## Media and names

Software licenses do not grant rights to other people's media. Download and share
only content you are permitted to use and comply with applicable service terms.
Service and project names describe integration, not affiliation or endorsement.
