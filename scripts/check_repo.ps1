$errors = @()

Write-Host "git status --short"
$status = git status --short
if ($status) {
    Write-Host $status
    $errors += "Working tree not clean"
}

Write-Host "`ngit ls-files .env out out_runs trade_history.csv grid_bot.db orders.json"
$tracked = git ls-files .env out out_runs trade_history.csv grid_bot.db orders.json 2>$null
if ($tracked) {
    Write-Host $tracked
    $errors += "Generated/sensitive files tracked in git"
}

Write-Host "`ngit grep -nI \"api|key|secret|token|pass|password|kucoin\""
$grep = git grep -nI "api|key|secret|token|pass|password|kucoin" 2>$null
if ($grep) {
    Write-Host $grep
    $errors += "Potential secrets found in repo"
}

Write-Host ""
if ($errors.Count -eq 0) {
    Write-Host "PASS: repo hygiene checks clean." -ForegroundColor Green
} else {
    Write-Host "FAIL:" -ForegroundColor Red
    $errors | ForEach-Object { Write-Host " - $_" -ForegroundColor Red }
    Write-Host ""
    Write-Host "Guidance: ensure sensitive files are untracked, rotate any exposed credentials, consider making repo private." -ForegroundColor Yellow
}
