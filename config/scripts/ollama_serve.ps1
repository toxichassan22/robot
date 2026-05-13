param(
  [string]$ModelsDir = "",
  [int]$Port = 11435
)

$ErrorActionPreference = "Stop"

if (-not $ModelsDir) {
  if (Test-Path "D:\models") {
    $ModelsDir = "D:\models"
  } else {
    $ModelsDir = (Resolve-Path ".\models\ollama" -ErrorAction SilentlyContinue).Path
    if (-not $ModelsDir) {
      $ModelsDir = (Join-Path (Get-Location) "models\ollama")
      New-Item -ItemType Directory -Force -Path $ModelsDir | Out-Null
    }
  }
}

$env:OLLAMA_MODELS = $ModelsDir
$env:OLLAMA_HOST = "127.0.0.1:$Port"

Write-Host "OLLAMA_MODELS=$env:OLLAMA_MODELS"
Write-Host "OLLAMA_HOST=$env:OLLAMA_HOST"

ollama serve

