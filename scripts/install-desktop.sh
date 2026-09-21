#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
applications_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$applications_dir"
python3 - "$project_dir" "$applications_dir" <<'PY'
from pathlib import Path
import sys
root, apps = map(Path, sys.argv[1:])

def desktop_string(value):
    return (value.replace('\\', '\\\\').replace('\n', '\\n')
            .replace('\r', '\\r').replace('\t', '\\t'))

def exec_argument(value):
    # Exec quoting is decoded after Desktop Entry string escaping.
    for char in ('\\', '"', '`', '$'):
        value = value.replace(char, '\\' + char)
    return desktop_string('"' + value.replace('%', '%%') + '"')

launcher = exec_argument(str(root / 'launch.sh'))
icon = desktop_string(str(root / 'src/mediagrab/assets/mediagrab.svg'))
content = f'''[Desktop Entry]
Type=Application
Name=MediaGrab
Comment=Download the copied media URL automatically
Exec={launcher}
Icon={icon}
Terminal=false
Categories=AudioVideo;Qt;
Keywords=video;image;media;download;clipboard;
StartupNotify=true
Actions=Advanced;

[Desktop Action Advanced]
Name=Full window
Exec={launcher} --advanced
Icon={icon}
'''
(apps / 'mediagrab.desktop').write_text(content)
print(apps / 'mediagrab.desktop')
PY
if command -v update-desktop-database >/dev/null; then
    update-desktop-database "$applications_dir"
fi
