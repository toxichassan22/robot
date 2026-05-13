param(
  [string]$ChatterboxRoot = ""
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
    "D:\robot new version\Chatterbox-TTS-Server-windows-easyInstallation-main\Chatterbox-TTS-Server-windows-easyInstallation-main"
  )

  foreach ($candidate in $candidates | Where-Object { $_ }) {
    $serverPath = Join-Path $candidate "server.py"
    if (Test-Path $serverPath) {
      return (Resolve-Path $candidate).Path
    }
  }

  throw "Could not locate the Chatterbox source folder."
}

$root = Resolve-ChatterboxRoot $ChatterboxRoot
$venvPython = Join-Path $root "venv\Scripts\python.exe"
$modelCacheRoot = Join-Path $root "model_cache"
$hfHome = Join-Path $modelCacheRoot ".hf-home"
$hfHubCache = Join-Path $hfHome "hub"
$transformersCache = Join-Path $hfHome "transformers"
$xdgCacheHome = Join-Path $modelCacheRoot ".xdg-cache"
$torchHome = Join-Path $modelCacheRoot ".torch"

if (-not (Test-Path $venvPython)) {
  throw "Chatterbox venv is missing. Run setup_chatterbox_local.ps1 first."
}

$env:HF_HOME = $hfHome
$env:HUGGINGFACE_HUB_CACHE = $hfHubCache
$env:TRANSFORMERS_CACHE = $transformersCache
$env:XDG_CACHE_HOME = $xdgCacheHome
$env:TORCH_HOME = $torchHome
$env:CHATTERBOX_OPEN_BROWSER = "0"
New-Item -ItemType Directory -Force -Path $modelCacheRoot, $hfHubCache, $transformersCache, $xdgCacheHome, $torchHome | Out-Null
Set-Location $root
& $venvPython .\server.py
