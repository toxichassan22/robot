param(
  [int]$Days = 7,
  [switch]$Apply,
  [switch]$Aggressive,
  [switch]$ClearRecycleBin,
  [switch]$Report,
  [int]$Top = 20,
  [int]$MaxDepth = 3,
  [switch]$ReportDeep,
  [switch]$VeryAggressive
)

$ErrorActionPreference = "Stop"

function Get-FolderSizeBytes {
  param([string]$Path)
  if (-not (Test-Path $Path)) { return 0 }
  try {
    $sum = (Get-ChildItem -LiteralPath $Path -Recurse -Force -File -ErrorAction SilentlyContinue |
      Measure-Object -Property Length -Sum).Sum
    if ($null -eq $sum) { return 0 }
    return [int64]$sum
  } catch {
    return 0
  }
}

function Get-LargestFolders {
  param(
    [string]$Root,
    [int]$Top = 20,
    [int]$MaxDepth = 3
  )
  if (-not (Test-Path $Root)) { return @() }
  $rootPath = (Resolve-Path -LiteralPath $Root).Path
  $rows = New-Object System.Collections.Generic.List[object]

  $stack = New-Object System.Collections.Generic.Stack[object]
  $stack.Push(@($rootPath, 0))

  while ($stack.Count -gt 0) {
    $item = $stack.Pop()
    $path = $item[0]
    $depth = [int]$item[1]
    try {
      $dirs = Get-ChildItem -LiteralPath $path -Directory -Force -ErrorAction SilentlyContinue
      foreach ($d in $dirs) {
        $size = Get-FolderSizeBytes -Path $d.FullName
        $rows.Add([pscustomobject]@{ Path = $d.FullName; SizeBytes = [int64]$size })
        if ($depth + 1 -lt $MaxDepth) {
          $stack.Push(@($d.FullName, $depth + 1))
        }
      }
    } catch {
    }
  }

  return $rows | Sort-Object SizeBytes -Descending | Select-Object -First $Top
}

function Get-TopLevelFolderSizes {
  param(
    [string]$Root,
    [int]$Top = 20
  )
  if (-not (Test-Path $Root)) { return @() }
  $rows = @()
  try {
    $dirs = Get-ChildItem -LiteralPath $Root -Directory -Force -ErrorAction SilentlyContinue
    foreach ($d in $dirs) {
      $size = Get-FolderSizeBytes -Path $d.FullName
      $rows += [pscustomobject]@{ Path = $d.FullName; SizeBytes = [int64]$size }
    }
  } catch {
  }
  return $rows | Sort-Object SizeBytes -Descending | Select-Object -First $Top
}

function Format-Bytes {
  param([int64]$Bytes)
  $units = @("B","KB","MB","GB","TB")
  $i = 0
  $v = [double]$Bytes
  while ($v -ge 1024 -and $i -lt $units.Length - 1) { $v = $v / 1024; $i++ }
  return ("{0:n2} {1}" -f $v, $units[$i])
}

function Remove-OldItems {
  param(
    [string]$Path,
    [int]$Days,
    [switch]$Apply
  )
  if (-not (Test-Path $Path)) {
    Write-Host "Skip (missing): $Path"
    return
  }
  $cutoff = (Get-Date).AddDays(-1 * $Days)
  $items = Get-ChildItem -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt $cutoff }

  if (-not $Apply) {
    Write-Host "Dry-run: would delete $($items.Count) items older than $Days days under: $Path"
    return
  }

  foreach ($it in $items) {
    try {
      Remove-Item -LiteralPath $it.FullName -Recurse -Force -ErrorAction SilentlyContinue
    } catch {
    }
  }
  Write-Host "Deleted old items under: $Path"
}

function Remove-Folder {
  param(
    [string]$Path,
    [switch]$Apply
  )
  if (-not (Test-Path $Path)) {
    Write-Host "Skip (missing): $Path"
    return
  }
  if (-not $Apply) {
    Write-Host "Dry-run: would delete folder: $Path"
    return
  }
  try {
    Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "Deleted: $Path"
  } catch {
    Write-Host "Failed to delete (in use?): $Path"
  }
}

function Get-DriveFree {
  param([string]$DriveName)
  try {
    $d = Get-PSDrive -Name $DriveName -ErrorAction Stop
    return [pscustomobject]@{ Name = $DriveName; Used = $d.Used; Free = $d.Free }
  } catch {
    return $null
  }
}

$pipCache1 = Join-Path $env:LOCALAPPDATA "pip\Cache"
$pipCache2 = Join-Path $env:LOCALAPPDATA "pip\cache"
$uvCache1 = Join-Path $env:LOCALAPPDATA "uv\cache"
$uvCache2 = Join-Path $env:APPDATA "uv\cache"
$npmCache1 = Join-Path $env:APPDATA "npm-cache"
$npmCache2 = Join-Path $env:LOCALAPPDATA "npm-cache"
$yarnCache1 = Join-Path $env:LOCALAPPDATA "Yarn\Cache"
$pnpmStore1 = Join-Path $env:LOCALAPPDATA "pnpm-store"
$nugetPackages = Join-Path $env:USERPROFILE ".nuget\packages"
$vscodeCache1 = Join-Path $env:APPDATA "Code\Cache"
$vscodeCache2 = Join-Path $env:APPDATA "Code\CachedData"
$vscodeCache3 = Join-Path $env:LOCALAPPDATA "Code\Cache"
$vscodeCache4 = Join-Path $env:LOCALAPPDATA "Code\CachedData"
$crashDumps = Join-Path $env:LOCALAPPDATA "CrashDumps"
$edgeCache = Join-Path $env:LOCALAPPDATA "Microsoft\Edge\User Data\Default\Cache"
$chromeCache = Join-Path $env:LOCALAPPDATA "Google\Chrome\User Data\Default\Cache"
$inetCache = Join-Path $env:LOCALAPPDATA "Microsoft\Windows\INetCache"
$arduino15 = Join-Path $env:LOCALAPPDATA "Arduino15"
$roblox = Join-Path $env:LOCALAPPDATA "Roblox"
$discordLocal = Join-Path $env:LOCALAPPDATA "Discord"
$zoomRoaming = Join-Path $env:APPDATA "Zoom"
$telegramRoaming = Join-Path $env:APPDATA "Telegram Desktop"
$comtypesCache1 = Join-Path $env:LOCALAPPDATA "comtypes"
$comtypesCache2 = Join-Path $env:APPDATA "comtypes"
$genPy = Join-Path $env:LOCALAPPDATA "Temp\gen_py"
$temp1 = $env:TEMP
$temp2 = $env:TMP

$targets = @(
  @{ Name = "pip cache"; Path = $pipCache1; Mode = "folder" },
  @{ Name = "pip cache"; Path = $pipCache2; Mode = "folder" },
  @{ Name = "uv cache"; Path = $uvCache1; Mode = "folder" },
  @{ Name = "uv cache"; Path = $uvCache2; Mode = "folder" },
  @{ Name = "npm cache"; Path = $npmCache1; Mode = "folder" },
  @{ Name = "npm cache"; Path = $npmCache2; Mode = "folder" },
  @{ Name = "yarn cache"; Path = $yarnCache1; Mode = "folder" },
  @{ Name = "pnpm store"; Path = $pnpmStore1; Mode = "folder" },
  @{ Name = "comtypes cache"; Path = $comtypesCache1; Mode = "folder" },
  @{ Name = "comtypes cache"; Path = $comtypesCache2; Mode = "folder" },
  @{ Name = "gen_py"; Path = $genPy; Mode = "folder" },
  @{ Name = "CrashDumps"; Path = $crashDumps; Mode = "folder" },
  @{ Name = "TEMP old"; Path = $temp1; Mode = "old" },
  @{ Name = "TMP old"; Path = $temp2; Mode = "old" }
)

$aggressiveTargets = @(
  @{ Name = "NuGet packages (will re-download)"; Path = $nugetPackages; Mode = "folder" },
  @{ Name = "VS Code cache"; Path = $vscodeCache1; Mode = "folder" },
  @{ Name = "VS Code cache"; Path = $vscodeCache2; Mode = "folder" },
  @{ Name = "VS Code cache"; Path = $vscodeCache3; Mode = "folder" },
  @{ Name = "VS Code cache"; Path = $vscodeCache4; Mode = "folder" },
  @{ Name = "Edge browser cache (close Edge first)"; Path = $edgeCache; Mode = "folder" },
  @{ Name = "Chrome browser cache (close Chrome first)"; Path = $chromeCache; Mode = "folder" },
  @{ Name = "INetCache"; Path = $inetCache; Mode = "folder" }
)

$veryAggressiveTargets = @(
  @{ Name = "Arduino15 (IDE boards cache; will re-download)"; Path = $arduino15; Mode = "folder" },
  @{ Name = "Roblox (will re-download)"; Path = $roblox; Mode = "folder" },
  @{ Name = "Discord (will re-download; may log out)"; Path = $discordLocal; Mode = "folder" },
  @{ Name = "Zoom data"; Path = $zoomRoaming; Mode = "folder" },
  @{ Name = "Telegram Desktop data"; Path = $telegramRoaming; Mode = "folder" }
)

$before = Get-DriveFree -DriveName "C"
if ($before -ne $null) {
  Write-Host ("C: Free before: {0}" -f (Format-Bytes -Bytes $before.Free))
}

Write-Host "Targets on C (user profile caches only). Apply=$Apply Days=$Days Aggressive=$Aggressive ClearRecycleBin=$ClearRecycleBin"
foreach ($t in $targets) {
  $size = Get-FolderSizeBytes -Path $t.Path
  if ($size -gt 0) {
    Write-Host ("- {0}: {1} ({2})" -f $t.Name, $t.Path, (Format-Bytes -Bytes $size))
  } else {
    Write-Host ("- {0}: {1}" -f $t.Name, $t.Path)
  }
}

if ($Aggressive) {
  Write-Host ""
  Write-Host "Aggressive targets:"
  foreach ($t in $aggressiveTargets) {
    $size = Get-FolderSizeBytes -Path $t.Path
    if ($size -gt 0) {
      Write-Host ("- {0}: {1} ({2})" -f $t.Name, $t.Path, (Format-Bytes -Bytes $size))
    } else {
      Write-Host ("- {0}: {1}" -f $t.Name, $t.Path)
    }
  }
}

if ($VeryAggressive) {
  Write-Host ""
  Write-Host "Very aggressive targets (close apps first):"
  foreach ($t in $veryAggressiveTargets) {
    $size = Get-FolderSizeBytes -Path $t.Path
    if ($size -gt 0) {
      Write-Host ("- {0}: {1} ({2})" -f $t.Name, $t.Path, (Format-Bytes -Bytes $size))
    } else {
      Write-Host ("- {0}: {1}" -f $t.Name, $t.Path)
    }
  }
}

if ($Report) {
  Write-Host ""
  if ($ReportDeep) {
    Write-Host "Largest folders report (deep; may take time):"
  } else {
    Write-Host "Largest folders report (fast):"
  }
  $roots = @(
    $env:USERPROFILE,
    (Join-Path $env:USERPROFILE "Downloads"),
    $env:LOCALAPPDATA,
    $env:APPDATA
  ) | Select-Object -Unique

  foreach ($r in $roots) {
    if (-not $r) { continue }
    if (-not (Test-Path $r)) { continue }
    Write-Host ""
    Write-Host ("Top {0} under: {1}" -f $Top, $r)
    if ($ReportDeep) {
      $largest = Get-LargestFolders -Root $r -Top $Top -MaxDepth $MaxDepth
    } else {
      $largest = Get-TopLevelFolderSizes -Root $r -Top $Top
    }
    foreach ($row in $largest) {
      Write-Host ("- {0} ({1})" -f $row.Path, (Format-Bytes -Bytes $row.SizeBytes))
    }
  }
}

Write-Host ""
Write-Host "Dry-run by default. Re-run with -Apply to actually delete."
Write-Host ""

foreach ($t in $targets) {
  if ($t.Mode -eq "folder") {
    Remove-Folder -Path $t.Path -Apply:$Apply
  } else {
    Remove-OldItems -Path $t.Path -Days $Days -Apply:$Apply
  }
}

if ($Aggressive) {
  foreach ($t in $aggressiveTargets) {
    Remove-Folder -Path $t.Path -Apply:$Apply
  }
}

if ($VeryAggressive) {
  foreach ($t in $veryAggressiveTargets) {
    Remove-Folder -Path $t.Path -Apply:$Apply
  }
}

if ($ClearRecycleBin) {
  if (-not $Apply) {
    Write-Host "Dry-run: would clear Recycle Bin"
  } else {
    try {
      Clear-RecycleBin -Force -ErrorAction SilentlyContinue | Out-Null
      Write-Host "Recycle Bin cleared"
    } catch {
      Write-Host "Failed to clear Recycle Bin"
    }
  }
}

$after = Get-DriveFree -DriveName "C"
if ($after -ne $null) {
  Write-Host ("C: Free after:  {0}" -f (Format-Bytes -Bytes $after.Free))
}
