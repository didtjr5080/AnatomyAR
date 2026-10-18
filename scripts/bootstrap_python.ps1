param([switch]$Offline)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$venvRoot = Join-Path $projectRoot '.venv'
$pythonExe = Join-Path $venvRoot 'Scripts\python.exe'

if (Test-Path -LiteralPath $pythonExe) {
    try {
        & $pythonExe -c "import sys,struct; assert sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8" 2>$null
        if ($LASTEXITCODE -eq 0) { exit 0 }
    } catch { }
}
if ($Offline) {
    throw 'Offline setup needs an existing Python 3.12 x64 .venv. Create it with: py -3.12 -m venv .venv'
}
if (Test-Path -LiteralPath $venvRoot) {
    if ((Split-Path -Parent $venvRoot) -ne $projectRoot) { throw 'Unexpected environment path' }
    $backupPath = Join-Path $projectRoot ('.venv.backup-' + [guid]::NewGuid().ToString('N'))
    Move-Item -LiteralPath $venvRoot -Destination $backupPath
    Write-Host "Preserved the unusable environment at $backupPath"
}

# A pinned portable installer stays inside the project; no PATH or registry changes.
$uvVersion = '0.10.7'
$uvHash = '8881afb877996a1373a12e816395122a8d39a3ac06cd066272acdb49510cf0fe'
$toolsRoot = Join-Path $projectRoot ".tools\uv-$uvVersion"
$uvExe = Join-Path $toolsRoot 'uv.exe'
if (-not (Test-Path -LiteralPath $uvExe)) {
    New-Item -ItemType Directory -Path $toolsRoot -Force | Out-Null
    $archive = Join-Path $toolsRoot 'uv.zip'
    $url = "https://github.com/astral-sh/uv/releases/download/$uvVersion/uv-x86_64-pc-windows-msvc.zip"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $archive -TimeoutSec 120
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $uvHash) {
        throw 'uv download checksum mismatch'
    }
    Expand-Archive -LiteralPath $archive -DestinationPath $toolsRoot -Force
}
if (-not (Test-Path -LiteralPath $uvExe)) { throw 'Portable uv executable is missing' }
$env:UV_CACHE_DIR = Join-Path $projectRoot '.uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $projectRoot '.python'
& $uvExe python install 3.12.8 --no-bin --no-registry
if ($LASTEXITCODE -ne 0) { throw 'Python download failed; check the internet connection and retry' }
& $uvExe venv --python 3.12.8 --managed-python --seed $venvRoot
if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment' }
& $pythonExe -c "import sys,struct; assert sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8"
if ($LASTEXITCODE -ne 0) { throw 'Python environment verification failed' }
