$sourceDir = "d:\robot new version"
Set-Location $sourceDir

# Add all changes
git add .

# Check if there are any changes to commit
$status = git status --porcelain
if ($status) {
    # Commit changes
    $date = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    git commit -m "Auto-sync backup $date"
    
    # Push to GitHub
    git push origin main
    
    Write-Host "Changes pushed to GitHub successfully at $date"
} else {
    Write-Host "No changes to commit."
}
