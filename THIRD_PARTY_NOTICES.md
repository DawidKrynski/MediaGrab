# Third-party notices

MediaGrab uses independently distributed open-source software. The dependencies
retain their own licenses; this file does not relicense them. MediaGrab's own
code and assets use the [MIT license](LICENSE). See the
[licensing and distribution scope](docs/LICENSING.md).

This inventory records the fresh Linux Python verification environment inspected on
2026-09-21. Versions are evidence of that environment, not a promise that a future
unconstrained install will resolve identically. License values came from installed
package metadata and available license files. Upstream terms and notices govern.
Dependency binaries, their complete notices, and their source code are not included
in this source tree. This summary is not a replacement for the full license texts
required when redistributing those dependencies.

## Direct runtime dependencies

| Component | Reviewed version | License declared by the package | Use / upstream |
| --- | --- | --- | --- |
| PySide6 | 6.11.2 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only; inspect the actual Qt modules and embedded components | GUI; [Qt for Python](https://doc.qt.io/qtforpython-6/licenses.html) |
| yt-dlp | 2026.8.19 | Unlicense for the PyPI package | Separate download process; [licensing and artifact differences](https://github.com/yt-dlp/yt-dlp#licensing) |
| gallery-dl | 1.32.13 | GPL-2.0-only | Separate download process; [license](https://github.com/mikf/gallery-dl/blob/master/LICENSE) |
| dbus-next | 0.2.3 | MIT | FileManager1 integration; [license](https://github.com/altdesktop/python-dbus-next/blob/master/LICENSE) |
| requests | 2.34.2 | Apache-2.0; package includes LICENSE and NOTICE | Thumbnail HTTP requests; [source](https://github.com/psf/requests) |

MediaGrab imports QtCore, QtGui, and QtWidgets. The PySide6 package also installs
Essentials, Addons, and shiboken6; this inventory does not imply every installed
Addons module is used or available under LGPL. See [Qt module licensing](https://doc.qt.io/qt-6/licensing.html).

## Runtime dependency packages and extras

| Package | Reviewed version | Declared license / scope |
| --- | --- | --- |
| brotli | 1.2.0 | MIT |
| certifi | 2026.7.22 | MPL-2.0 |
| cffi | 2.1.1 | MIT-0; embedded native components must be checked separately |
| charset-normalizer | 3.5.1 | MIT |
| curl_cffi | 0.16.3 | MIT for the Python binding; not a complete license inventory for its native wheel payload |
| idna | 3.20 | BSD-3-Clause |
| mutagen | 1.48.1 | GPL-2.0-or-later |
| pycparser | 3.0 | BSD-3-Clause |
| pycryptodomex | 3.23.0 | BSD-2-Clause and public-domain portions, as described in its LICENSE.rst |
| PySide6_Addons | 6.11.2 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only metadata; actual Qt module terms apply |
| PySide6_Essentials | 6.11.2 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only metadata; embedded third-party terms also apply |
| shiboken6 | 6.11.2 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |
| typing_extensions | 4.16.0 | PSF-2.0 |
| urllib3 | 2.8.0 | MIT |
| websockets | 17.1 | BSD-3-Clause |
| yt-dlp-ejs | 0.8.0 | Unlicense AND MIT AND ISC, including its embedded JavaScript components |

The yt-dlp project documents its [optional dependencies and their licenses](https://github.com/yt-dlp/yt-dlp#dependencies).
The curl-cffi project is maintained at [lexiforest/curl_cffi](https://github.com/lexiforest/curl_cffi).

## Development and installation tools

These packages were present in the reviewed environment; they are not application
runtime imports.

| Package | Reviewed version | Declared license |
| --- | --- | --- |
| iniconfig | 2.3.0 | MIT |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pip | 26.1.2 | MIT for pip itself; vendored packages carry additional licenses |
| pluggy | 1.6.0 | MIT |
| Pygments | 2.21.0 | BSD-2-Clause |
| pytest | 9.1.1 | MIT |
| pytest-qt | 4.5.0 | MIT |
| ruff | 0.16.8 | MIT for the package; native build dependencies require their own review if redistributed |

Setuptools is selected in an isolated build environment by `pyproject.toml` and
was not installed in this environment. A distributable toolchain or bundled build
environment needs its own exact-version inventory.

## External system programs

- **FFmpeg and ffprobe:** not bundled. License depends on the build and enabled
  components; see [FFmpeg license guidance](https://ffmpeg.org/legal.html).
- **Node.js:** not bundled. Node has an MIT license and includes dependencies with
  additional notices; see the [upstream license](https://github.com/nodejs/node/blob/main/LICENSE).
- **Python:** supplied by the installation environment and not bundled; see
  [Python's license](https://docs.python.org/3/license.html).

For a frozen executable, AppImage, wheelhouse, virtual-environment archive, or
container image, inventory the actual contents and supply their complete notices
and any required corresponding source. See [distribution review requirements](docs/LICENSING.md#bundled-distributions-require-another-review).
