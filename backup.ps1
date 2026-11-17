# Inventory DB Backup Script
$DB    = "$PSScriptRoot\inventory.db"
$STAMP = Get-Date -Format "yyyy-MM-dd_HH-mm"
$FNAME = "inventory_$STAMP.db"

$TARGETS = @(
    "$PSScriptRoot\backups",
    "D:\inventory_backups"
)

if (-not (Test-Path $DB)) {
    Write-Host "ERROR: DB not found -- $DB" -ForegroundColor Red
    pause; exit 1
}

$ok = 0
foreach ($dir in $TARGETS) {
    try {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        $dst = Join-Path $dir $FNAME
        Copy-Item -Path $DB -Destination $dst -ErrorAction Stop
        $sz = [math]::Round((Get-Item $dst).Length / 1KB, 1)
        Write-Host "OK  $dst  ($sz KB)" -ForegroundColor Green
        $ok++
    } catch {
        Write-Host "FAIL $dir  -- $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "Backup done: $ok / $($TARGETS.Count) locations  [$STAMP]" -ForegroundColor Cyan
pause
