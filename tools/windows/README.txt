MediaGrab for Windows (portable)
================================

Copy a link. Save its videos and images.

Start
-----
1. Keep this whole folder together; MediaGrab.exe needs the files next to it.
2. Copy one media URL, then double-click MediaGrab.exe.
3. Files are saved to Downloads\Media\<source>\ and Explorer opens them.
   No link in the clipboard? Paste it into the small window and press Enter.
   Right-click the link field and choose "Full window" to pick individual items.

No Python installation is needed. mediagrab-engine.exe is an internal helper that
runs the bundled yt-dlp and gallery-dl; do not start it directly.

Additional programs
-------------------
- Videos: install FFmpeg (ffmpeg.exe and ffprobe.exe) on PATH, for example
  "winget install Gyan.FFmpeg" or a build from https://ffmpeg.org/download.html.
  Images work without it.
- YouTube: install a JavaScript runtime supported by yt-dlp, for example Deno
  ("winget install DenoLand.Deno"). Node.js is used when it is on PATH.
  See https://github.com/yt-dlp/yt-dlp/wiki/EJS
Restart MediaGrab after installing either program.

Use an NTFS download folder. Download only media you are entitled to save.
Settings are stored in HKEY_CURRENT_USER\Software\MediaGrab\MediaGrab.
To remove MediaGrab, delete this folder (and optionally that registry key).

Licenses
--------
MediaGrab is MIT licensed (LICENSE.txt). Bundled components keep their own
licenses: see THIRD_PARTY_NOTICES.txt. Source code of bundled copyleft Python
packages is in the sources folder; MediaGrab's source is at
https://github.com/DawidKrynski/MediaGrab
