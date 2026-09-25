"""PyInstaller entry point of mediagrab-engine.exe in the portable Windows package."""

import sys

from mediagrab.engine import main

sys.exit(main())
