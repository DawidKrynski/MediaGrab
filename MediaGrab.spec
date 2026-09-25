# Portable Windows build; run tools/build_windows.ps1 instead of calling this directly.
# One folder, two executables sharing _internal: the windowed GUI and the console
# engine helper that runs the bundled yt-dlp and gallery-dl as separate processes.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH)
icon = root / 'build' / 'windows' / 'mediagrab.ico'
utf8 = [('X utf8_mode=1', None, 'OPTION')]
common_excludes = ['tkinter', 'pytest', 'pytestqt', 'PyQt5', 'PyQt6', 'PySide2', 'IPython']

gui = Analysis(
    [str(root / 'tools' / 'windows' / 'mediagrab_gui.py')],
    pathex=[str(root / 'src')],
    datas=collect_data_files('mediagrab') + copy_metadata('mediagrab'),
    hiddenimports=['mediagrab.quick', 'mediagrab._windows'],
    excludes=common_excludes + ['yt_dlp', 'gallery_dl', 'curl_cffi', 'mutagen'],
    noarchive=False,
)
engine = Analysis(
    [str(root / 'tools' / 'windows' / 'mediagrab_engine.py')],
    pathex=[str(root / 'src')],
    datas=(
        collect_data_files('yt_dlp_ejs') + collect_data_files('gallery_dl')
        + copy_metadata('yt-dlp') + copy_metadata('gallery-dl') + copy_metadata('yt-dlp-ejs')
    ),
    hiddenimports=(
        collect_submodules('yt_dlp') + collect_submodules('gallery_dl')
        + collect_submodules('yt_dlp_ejs') + ['yt_dlp.__main__', 'gallery_dl.__main__']
    ),
    excludes=common_excludes + ['PySide6', 'shiboken6'],
    noarchive=False,
)

# Widgets-only GUI: drop Qt Quick/QML (pulled in by the virtual keyboard input plugin),
# the PDF image plugin, and the software OpenGL fallback, which MediaGrab never uses.
UNUSED_QT = ('qt6pdf', 'qt6qml', 'qt6quick', 'qt6virtualkeyboard', 'qpdf', 'virtualkeyboard',
             'opengl32sw')
gui.binaries = [
    entry for entry in gui.binaries
    if not any(part in Path(entry[0]).name.lower() for part in UNUSED_QT)
]
gui.datas = [
    entry for entry in gui.datas if 'qml' not in Path(entry[0]).parts
]

gui_exe = EXE(
    PYZ(gui.pure), gui.scripts, [], utf8, exclude_binaries=True,
    name='MediaGrab', console=False, icon=str(icon) if icon.is_file() else None,
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
)
engine_exe = EXE(
    PYZ(engine.pure), engine.scripts, [], utf8, exclude_binaries=True,
    name='mediagrab-engine', console=True, icon=str(icon) if icon.is_file() else None,
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
)
COLLECT(
    gui_exe, gui.binaries, gui.datas,
    engine_exe, engine.binaries, engine.datas,
    name='MediaGrab', strip=False, upx=False,
)
