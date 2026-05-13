$ErrorActionPreference = "Stop"

$projectRoot = (Get-Location).Path
$cacheRoot = Join-Path $projectRoot ".cache"

New-Item -ItemType Directory -Force -Path (Join-Path $cacheRoot "pip") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $cacheRoot "tmp") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $cacheRoot "comtypes") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $cacheRoot "pycache") | Out-Null

$env:PIP_CACHE_DIR = (Join-Path $cacheRoot "pip")
$env:TEMP = (Join-Path $cacheRoot "tmp")
$env:TMP = (Join-Path $cacheRoot "tmp")
$env:COMTYPES_CACHE_DIR = (Join-Path $cacheRoot "comtypes")
$env:PYTHONPYCACHEPREFIX = (Join-Path $cacheRoot "pycache")

$activate = Join-Path $projectRoot ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $activate)) {
  throw "Virtual env not found at .venv. Create it with: python -m venv .venv"
}

& $activate
Write-Host "Dev shell ready. Cache+temp pinned to: $cacheRoot"

