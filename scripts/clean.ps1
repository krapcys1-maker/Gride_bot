$paths = @(
    "out",
    "out_runs",
    "__pycache__",
    ".pytest_cache",
    "*.pyc",
    "*.db",
    "trade_history.csv",
    "grid_bot.db"
)

foreach ($p in $paths) {
    Get-ChildItem -Path $p -ErrorAction SilentlyContinue | ForEach-Object {
        if (Test-Path $_.FullName) {
            Write-Host "Removing $($_.FullName)"
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $_.FullName
        }
    }
}
