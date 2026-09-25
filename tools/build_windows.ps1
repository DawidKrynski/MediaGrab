# Build the portable Windows x64 package: dist\MediaGrab-Windows-x64.zip + SHA256SUMS.txt.
# Requires Windows x64, uv on PATH and network access for the pinned dependencies and
# copyleft source archives. FFmpeg/ffprobe on PATH enable the real-engine video tests.
param([string]$Python = '3.13')

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$env:PYTHONUTF8 = '1'
$env:QT_QPA_PLATFORM = 'offscreen'

function Invoke-Step([string]$Message, [scriptblock]$Command) {
    Write-Host "== $Message"
    # Native tools report progress on stderr; judge them by exit code only.
    $ErrorActionPreference = 'Continue'
    & $Command
    if ($LASTEXITCODE) { throw "$Message failed (exit $LASTEXITCODE)" }
}

if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitOperatingSystem) {
    throw 'The portable package must be built on 64-bit Windows.'
}
$work = Join-Path $root 'build\windows'
$dist = Join-Path $root 'dist'
foreach ($path in @($work, (Join-Path $dist 'MediaGrab'))) {
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force }
}
New-Item -ItemType Directory $work, $dist -Force | Out-Null
$venv = Join-Path $work 'venv'
$py = Join-Path $venv 'Scripts\python.exe'

Invoke-Step 'Create build environment' { uv venv --python $Python $venv }
Invoke-Step 'Install pinned dependencies' {
    uv pip sync --python $py --require-hashes tools\windows\requirements-build.txt
}
Invoke-Step 'Install MediaGrab' { uv pip install --python $py --no-deps . }
Invoke-Step 'Dependency check' { uv pip check --python $py }
Invoke-Step 'Lint' { & $py -m ruff check . }
Invoke-Step 'Tests' { & $py -m pytest -q --integration -p no:cacheprovider }
Invoke-Step 'Collect notices and sources' { & $py tools\third_party_notices.py $work }
Invoke-Step 'Create icon' {
    @'
import sys
from pathlib import Path
from PySide6.QtGui import QGuiApplication, QPixmap
import mediagrab
app = QGuiApplication([])
image = QPixmap(str(Path(mediagrab.__file__).with_name("assets") / "mediagrab.svg"))
sys.exit(0 if image.save(sys.argv[1], "ICO") else 1)
'@ | & $py - (Join-Path $work 'mediagrab.ico')
}
Invoke-Step 'PyInstaller' {
    & $py -m PyInstaller --clean --noconfirm --distpath (Join-Path $work 'dist') `
        --workpath (Join-Path $work 'pyinstaller') MediaGrab.spec
}
Invoke-Step 'Assemble portable folder' {
    & $py tools\windows\package.py assemble (Join-Path $work 'dist\MediaGrab') $work $dist
}

# Exercise a copy outside the checkout: engines through the frozen helper, the
# real-engine loopback tests with that helper, and a GUI start without Python.
$test = Join-Path ([IO.Path]::GetTempPath()) ('mediagrab-portable-' + [guid]::NewGuid())
New-Item -ItemType Directory $test | Out-Null
try {
    Copy-Item (Join-Path $dist 'MediaGrab') $test -Recurse
    $app = Join-Path $test 'MediaGrab'
    $engine = Join-Path $app 'mediagrab-engine.exe'
    Invoke-Step 'Bundled engine versions' {
        $script:ytdlp = (& $engine -m yt_dlp --version | Out-String).Trim()
        if (-not $LASTEXITCODE) {
            $script:gallery = (& $engine -m gallery_dl --version | Out-String).Trim()
        }
    }
    if (-not $ytdlp -or -not $gallery) { throw 'Bundled engines reported no version' }
    $refused = Start-Process -FilePath $engine -ArgumentList '-c', 'print(1)' -Wait -PassThru `
        -NoNewWindow -RedirectStandardError (Join-Path $test 'refused.txt')
    if ($refused.ExitCode -ne 2) { throw 'The engine helper accepted arbitrary code' }
    Invoke-Step 'Real-engine tests with the frozen helper' {
        & $py -m pytest -q --integration -p no:cacheprovider tests\test_integration.py `
            --engine-helper $engine
    }
    $gui = Start-Process -FilePath (Join-Path $app 'MediaGrab.exe') -ArgumentList '--advanced' `
        -WorkingDirectory $test -PassThru
    Start-Sleep -Seconds 8
    if ($gui.HasExited) { throw "MediaGrab.exe exited early (exit $($gui.ExitCode))" }
    Stop-Process -Id $gui.Id -Force
    [ordered]@{
        ok = $true; yt_dlp = $ytdlp; gallery_dl = $gallery
        ffmpeg = [bool](Get-Command ffmpeg -ErrorAction SilentlyContinue)
    } | ConvertTo-Json | Set-Content (Join-Path $dist 'windows-smoke.json') -Encoding utf8
} finally {
    Remove-Item -LiteralPath $test -Recurse -Force -ErrorAction SilentlyContinue
}

Invoke-Step 'Create ZIP and checksums' { & $py tools\windows\package.py archive $dist }
Write-Host "Built dist\MediaGrab-Windows-x64.zip. No Python installation is needed to run it."
