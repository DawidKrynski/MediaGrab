$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectDir = Split-Path -Parent $PSScriptRoot
$environmentDir = Join-Path $projectDir '.venv'
$pythonPath = Join-Path $environmentDir 'Scripts\python.exe'
$pythonWindowPath = Join-Path $environmentDir 'Scripts\pythonw.exe'

try {
    if ($env:OS -ne 'Windows_NT') { throw 'This installer requires Windows.' }
    foreach ($tool in @('ffmpeg', 'ffprobe')) {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
            throw "Install FFmpeg (including $tool) on PATH, then run this installer again. See docs/DEVELOPMENT.md."
        }
    }
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            $pythonCommand = 'py'
            $pythonArguments = @('-3')
        } elseif (Get-Command python -ErrorAction SilentlyContinue) {
            $pythonCommand = 'python'
            $pythonArguments = @()
        } else {
            throw 'Install Python 3.11 or newer from python.org, then run this installer again.'
        }
        & $pythonCommand @pythonArguments -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or newer is required.' }
        & $pythonCommand @pythonArguments -m venv $environmentDir
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the private Python environment.' }
    }
    & $pythonPath -m pip install --upgrade $projectDir
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
    & $pythonPath -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'The Python dependency check failed.' }
    if (-not (Test-Path -LiteralPath $pythonWindowPath)) {
        throw 'The Python environment has no pythonw.exe GUI launcher.'
    }

    $iconPath = Join-Path $environmentDir 'mediagrab.ico'
    @'
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtGui import QGuiApplication, QPixmap
from pathlib import Path
import mediagrab
import sys
app = QGuiApplication([])
image = QPixmap(str(Path(mediagrab.__file__).with_name("assets") / "mediagrab.svg"))
sys.exit(0 if image.save(sys.argv[1], "ICO") else 1)
'@ | & $pythonPath - $iconPath
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Start menu icon.' }

    $programsDir = [Environment]::GetFolderPath('Programs')
    $desktopShell = New-Object -ComObject WScript.Shell
    foreach ($entry in @(
        @{ Name = 'MediaGrab'; Arguments = '-m mediagrab' },
        @{ Name = 'MediaGrab - Full window'; Arguments = '-m mediagrab --advanced' }
    )) {
        $shortcut = $desktopShell.CreateShortcut((Join-Path $programsDir ($entry.Name + '.lnk')))
        $shortcut.TargetPath = $pythonWindowPath
        $shortcut.Arguments = $entry.Arguments
        $shortcut.WorkingDirectory = $projectDir
        $shortcut.IconLocation = $iconPath
        $shortcut.Description = 'Save videos and images from a copied media link'
        $shortcut.Save()
    }
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        Write-Host 'For YouTube, also install a Node.js version supported by yt-dlp.'
    }
    Write-Host 'Open MediaGrab from the Start menu. Keep this checkout in place.'
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
