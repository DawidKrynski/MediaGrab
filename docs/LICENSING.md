# Licensing

Review date: 2026-09-21; portable Windows package reviewed 2026-09-25.

MediaGrab's own source code and assets are covered by the [MIT license](../LICENSE).
Its dependencies retain their respective licenses; MIT does not relicense them.
MediaGrab integrates independently installed downloaders rather than incorporating
their source code.

## Current source distribution

The repository contains the application, its own icon and screenshots, tests,
documentation, and the Windows build tooling, including verbatim license texts
used by the portable package (`tools/windows/licenses/`). It does not contain
downloader sources, dependency wheels, native libraries, or a bundled Python
environment. The application-only Python wheel also declares dependencies for
separate installation. The portable Windows ZIP is a separate, bundled
distribution; see [below](#portable-windows-package).

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

## Portable Windows package

`MediaGrab-Windows-x64.zip` is built by `tools/build_windows.ps1` with PyInstaller.
It contains MediaGrab, a CPython 3.13 runtime (with OpenSSL, libffi, SQLite,
bzip2, xz, zlib, and Microsoft Visual C++ runtime DLLs), Qt 6/PySide6 (Core, GUI,
Widgets, SVG, Network, and their plugins), yt-dlp with yt-dlp-ejs, gallery-dl,
curl_cffi with its libcurl-impersonate DLL, and their Python dependencies. The
build installs PySide6 Addons as a dependency of PySide6 but the packaging step
fails if any Addons binary is shipped.

How the package meets the reviewed obligations:

- **Notices:** `THIRD_PARTY_NOTICES.txt` in the ZIP lists every bundled Python
  distribution with its version and declared license and reproduces its license
  files, the Python license, the LGPLv3 and GPLv3 texts for Qt/PySide6 (whose
  wheels ship none), Qt's third-party attributions for the bundled modules, the
  license headers embedded in the yt-dlp JavaScript solvers, and the licenses of
  libraries statically linked into libcurl-impersonate (curl, BoringSSL, nghttp2,
  ngtcp2, nghttp3, Brotli, zstd, zlib).
- **Copyleft source:** the `sources` folder carries the exact PyPI source archives
  of gallery-dl (GPL-2.0-only), mutagen (GPL-2.0-or-later), and certifi (MPL-2.0),
  checked against PyPI's SHA-256 digests. MediaGrab's own source is this repository.
- **Qt/PySide6 (LGPLv3):** used unmodified as separate DLL/PYD files in
  `_internal\PySide6`, which users can replace with compatible builds. The notices
  point to the exact Qt for Python and Qt source releases on download.qt.io
  instead of shipping the Qt sources.
- **PyInstaller:** its bootloader is GPL-2.0 with an exception that permits
  distributing it with any program.

Decisions:

- **FFmpeg/ffprobe are not bundled.** Suitable Windows builds (Gyan: GPLv3 with
  many external libraries; BtbN: LGPL/GPL variants) oblige a redistributor to
  provide the complete corresponding source of FFmpeg and every linked library
  for that exact build. BtbN keeps daily builds for only 14 days, so upstream
  links cannot be relied on for the required availability, and hosting those
  sources would multiply the package size. Users install FFmpeg separately
  (for example `winget install Gyan.FFmpeg`); images work without it.
- **No JavaScript runtime is bundled.** yt-dlp needs Deno, Node, or QuickJS only
  for YouTube; Deno is enabled by default when it is on PATH, and MediaGrab adds
  Node when found. Bundling one would add a large separately licensed binary.

Open points before publishing a release:

- Qt/PySide6 corresponding source is provided by reference to download.qt.io,
  not in the release. If that is not considered sufficient, attach the matching
  Qt for Python and Qt source archives to the release or add a written offer.
- The helper process combines gallery-dl (GPL-2.0-only) with Apache-2.0 code
  (requests, Python's OpenSSL 3, BoringSSL). The FSF considers Apache-2.0
  incompatible with GPLv2-only. gallery-dl's own Windows executable is a PyInstaller
  build with the same combination; this is noted as a residual risk, not
  resolved legal advice.
- yt-dlp documents its own PyInstaller executables as GPLv3+ combined works
  (GPL-2.0-or-later mutagen together with Apache-2.0 components). In MediaGrab's
  helper, GPL-2.0-only gallery-dl joins that combination, which is why the
  previous point matters. MediaGrab's own code remains MIT licensed.
