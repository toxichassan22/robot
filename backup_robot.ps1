$sourceDir = "d:\robot new version"
$drivePath = "G:\My Drive"
$desktopPath = [Environment]::GetFolderPath("Desktop")

if (Test-Path $drivePath) {
    $zipPath = Join-Path $drivePath "Robot_Backup.zip"
} else {
    $zipPath = Join-Path $desktopPath "Robot_Backup.zip"
    Write-Host "Google Drive (G:) not found! Saving to Desktop instead." -ForegroundColor Yellow
}

$tempDir = Join-Path $env:TEMP "RobotBackupTemp"

Write-Host "Creating backup..." -ForegroundColor Cyan

# 1. Delete temp dir if exists
if (Test-Path $tempDir) { Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue }
New-Item -ItemType Directory -Path $tempDir | Out-Null

# 2. Copy files excluding heavy folders
Write-Host "Copying files (skipping heavy folders)..."
# /XD = eXclude Directories
# /XF = eXclude Files
# /MIR = MIRror directory tree
# /NJH /NJS /NDL /NC /NS = reduce logging noise
robocopy $sourceDir $tempDir /MIR /XD "venv" "node_modules" ".git" ".tmp.driveupload" "__pycache__" ".pytest_cache" "python310-embed" "vosk-model" "ffmpeg" "models" /XF "*.zip" /NJH /NJS /NDL /NC /NS /NFL

# 3. Zip the copied files
Write-Host "Compressing to $zipPath ..."
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path "$tempDir\*" -DestinationPath $zipPath -Force

# 4. Clean up
Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "Backup completed successfully!" -ForegroundColor Green
Write-Host "You can find your backup at: $zipPath" -ForegroundColor Yellow
Start-Sleep -Seconds 5
