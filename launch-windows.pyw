"""Double-click launcher for a Windows source installation (no console window)."""

import ctypes
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent
python = root / ".venv" / "Scripts" / "pythonw.exe"
if not python.is_file():
    ctypes.windll.user32.MessageBoxW(
        None,
        "Run Install-Windows.cmd first, then open MediaGrab from the Start menu.",
        "MediaGrab setup required",
        0x40,
    )
else:
    arguments = ["--advanced"] if "--advanced" in sys.argv[1:] else []
    subprocess.Popen([str(python), "-m", "mediagrab", *arguments], cwd=root)
