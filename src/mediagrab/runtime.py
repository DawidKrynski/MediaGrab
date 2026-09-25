"""Helper-process commands for source installations and the portable Windows build.

A source installation starts the engines with its own Python interpreter. The
portable build has no interpreter; its console helper, next to the GUI executable,
accepts the same ``-m <engine>`` arguments for the bundled engines only.
"""

from pathlib import Path
import sys

ENGINE_EXECUTABLE = "mediagrab-engine.exe"
ENGINE_MODULES = frozenset({"yt_dlp", "gallery_dl"})

# The bootstrap cannot spawn the engine before a Windows job owns it. If the parent
# exits before assignment, stdin reaches EOF and the bootstrap exits childless.
BOOTSTRAP = """
import subprocess, sys
if sys.stdin.buffer.read(1) != b'1':
    sys.exit(1)
try:
    result = subprocess.run(sys.argv[1:], stdin=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NO_WINDOW)
except FileNotFoundError:
    sys.stderr.write('ERROR: A required program is missing; no module named engine\\n')
    sys.exit(127)
sys.exit(result.returncode)
"""


def frozen():
    return bool(getattr(sys, "frozen", False))


def helper_python():
    """Interpreter-compatible executable for engine and bootstrap processes."""
    if frozen():
        return str(Path(sys.executable).with_name(ENGINE_EXECUTABLE))
    return sys.executable


def engine_command(module):
    if module not in ENGINE_MODULES:
        raise ValueError(f"Unsupported engine module: {module}")
    return [helper_python(), "-m", module]


def application_command(*args):
    if frozen():
        return [sys.executable, *args]
    return [sys.executable, "-m", "mediagrab", *args]
