param(
    [Parameter(Mandatory = $true)]
    [string]$OutDir,
    [string]$BaselineDir,
    [string]$Config = "tests/fixtures/config_costs_neutral_mix70.yaml",
    [int]$GridLevels = 4,
    [bool]$PanicEnabled = $true
)

$ErrorActionPreference = "Stop"

if (Test-Path $OutDir) {
    Remove-Item -Recurse -Force $OutDir
}

$panicValue = if ($PanicEnabled) { "true" } else { "false" }

python -m gridbot.tools.batch_run `
    --strategy-ids classic_grid `
    --scenarios range,trend_up,trend_down,flash_crash `
    --seeds 1,2,3,4,5,6,7,8,9,10 `
    --steps 2000 `
    --parallel 6 `
    --out-dir $OutDir `
    --config $Config `
    --grid-levels $GridLevels `
    --set "panic_enabled=$panicValue" `
    --interval 0 `
    --log-level WARNING

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if ($BaselineDir) {
    python -m gridbot.tools.eval_synth --out-dir $OutDir --baseline-dir $BaselineDir
}
else {
    python -m gridbot.tools.eval_synth --out-dir $OutDir
}
