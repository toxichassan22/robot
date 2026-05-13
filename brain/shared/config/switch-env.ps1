param(
  [Parameter(Mandatory=$true)]
  [ValidateSet("dev","prod")]
  [string]$Env
)

$root = Split-Path -Parent $PSScriptRoot
$src = Join-Path $PSScriptRoot ("config.{0}.json" -f $Env)
$dst = Join-Path $PSScriptRoot "config.json"

Copy-Item -Force $src $dst
Write-Output ("Switched config to {0}" -f $Env)

