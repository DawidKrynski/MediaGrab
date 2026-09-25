"""Console helper of the portable Windows build.

It emulates only the interpreter arguments MediaGrab itself uses: ``-m`` for the
bundled engines and ``-c`` for the exact Windows job bootstrap. Anything else is
refused, so the helper is not a general-purpose Python interpreter.
"""

import runpy
import sys

from .runtime import BOOTSTRAP, ENGINE_MODULES

USAGE = "mediagrab-engine: internal helper of MediaGrab; start MediaGrab.exe instead.\n"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) >= 2 and argv[0] == "-m" and argv[1] in ENGINE_MODULES:
        sys.argv = [argv[1], *argv[2:]]
        runpy.run_module(argv[1], run_name="__main__", alter_sys=True)
        return 0
    if len(argv) >= 2 and argv[0] == "-c" and argv[1] == BOOTSTRAP:
        sys.argv = ["-c", *argv[2:]]
        exec(compile(BOOTSTRAP, "<bootstrap>", "exec"), {"__name__": "__main__"})
        return 0
    sys.stderr.write(USAGE)
    return 2
