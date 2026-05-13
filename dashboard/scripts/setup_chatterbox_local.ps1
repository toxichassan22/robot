param(
  [string]$ChatterboxRoot = "",
  [ValidateSet("cpu", "nvidia", "amd")]
  [string]$Mode = "cpu"
)

$ErrorActionPreference = "Stop"

function Resolve-ChatterboxRoot([string]$ExplicitPath) {
  $candidates = @()

  if ($ExplicitPath) {
    $candidates += $ExplicitPath
  }

  if ($env:ROBOT_CHATTERBOX_ROOT) {
    $candidates += $env:ROBOT_CHATTERBOX_ROOT
  }

  $candidates += @(
    "D:\robot new version\Chatterbox-TTS-Server-windows-easyInstallation-main\Chatterbox-TTS-Server-windows-easyInstallation-main",
    (Join-Path (Split-Path $PSScriptRoot -Parent | Split-Path -Parent | Split-Path -Parent) "Chatterbox-TTS-Server-windows-easyInstallation-main\Chatterbox-TTS-Server-windows-easyInstallation-main")
  )

  foreach ($candidate in $candidates | Where-Object { $_ }) {
    $serverPath = Join-Path $candidate "server.py"
    if (Test-Path $serverPath) {
      return (Resolve-Path $candidate).Path
    }
  }

  throw "Could not locate the Chatterbox source folder."
}

function Get-Python310() {
  $launcher = Get-Command py -ErrorAction SilentlyContinue
  if (-not $launcher) {
    throw "The py launcher is not installed. Python 3.10 is required."
  }

  $pythonPath = & py -3.10 -c "import sys; print(sys.executable)" 2>$null
  if (-not $pythonPath) {
    throw "Python 3.10 was not found on this machine."
  }

  return $pythonPath.Trim()
}

$root = Resolve-ChatterboxRoot $ChatterboxRoot
$python310 = Get-Python310
$venvPython = Join-Path $root "venv\Scripts\python.exe"
$venvPip = Join-Path $root "venv\Scripts\pip.exe"
$modelCacheRoot = Join-Path $root "model_cache"
$hfHome = Join-Path $modelCacheRoot ".hf-home"
$hfHubCache = Join-Path $hfHome "hub"
$transformersCache = Join-Path $hfHome "transformers"
$xdgCacheHome = Join-Path $modelCacheRoot ".xdg-cache"
$torchHome = Join-Path $modelCacheRoot ".torch"

$env:HF_HOME = $hfHome
$env:HUGGINGFACE_HUB_CACHE = $hfHubCache
$env:TRANSFORMERS_CACHE = $transformersCache
$env:XDG_CACHE_HOME = $xdgCacheHome
$env:TORCH_HOME = $torchHome

New-Item -ItemType Directory -Force -Path $modelCacheRoot, $hfHubCache, $transformersCache, $xdgCacheHome, $torchHome | Out-Null
Set-Location $root

Write-Host ""
Write-Host "Chatterbox setup"
Write-Host "================"
Write-Host "Root   : $root"
Write-Host "Python : $python310"
Write-Host "Mode   : $Mode"
Write-Host "Cache  : $modelCacheRoot"
Write-Host ""

if (-not (Test-Path $venvPython)) {
& $python310 -m venv (Join-Path $root "venv")
}

& $venvPython -m pip install --upgrade pip

$requirementsName = switch ($Mode) {
  "nvidia" { "requirements-nvidia.txt" }
  "amd" { "requirements-rocm.txt" }
  default { "requirements.txt" }
}

$requirementsPath = Join-Path $root $requirementsName
if (-not (Test-Path $requirementsPath)) {
  throw "Requirements file was not found: $requirementsPath"
}

& $venvPip install -r $requirementsPath
& $venvPip install hf_xet
Write-Host ""
Write-Host "Preloading Chatterbox model files into local model_cache..."
& $venvPython (Join-Path $root "download_model.py")

Write-Host ""
Write-Host "Chatterbox is ready."
Write-Host "Run from the source folder with:"
Write-Host "  .\\venv\\Scripts\\python.exe .\\server.py"
