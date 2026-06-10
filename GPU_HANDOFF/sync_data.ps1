# sync_data.ps1 — Sync data + experiments from CPU machine to GPU machine.
#
# Run on the GPU machine. Pulls from the CPU machine via SCP/rsync.
# Requires SSH access from GPU machine -> CPU machine (or shared network drive).
#
# USAGE — edit the variables below first:
$SOURCE_HOST = "192.168.1.X"      # CPU machine IP (or hostname)
$SOURCE_USER = "user"             # CPU machine username
$SOURCE_BASE = "d:/pythone/freqtrade_btc_bot"  # path on CPU machine
$DEST_BASE = "$PSScriptRoot/.."   # local freqtrade_btc_bot dir

# Pre-check: ssh + scp available
if (-not (Get-Command scp -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: scp not found. Install OpenSSH client: Settings -> Apps -> Optional Features -> OpenSSH" -ForegroundColor Red
    exit 1
}

Write-Host "=== Sync from CPU machine ===" -ForegroundColor Cyan
Write-Host "From: ${SOURCE_USER}@${SOURCE_HOST}:${SOURCE_BASE}" -ForegroundColor Gray
Write-Host "To:   $DEST_BASE" -ForegroundColor Gray
Write-Host ""

# Items to sync (each item: source subdir → local destination subdir)
$items = @(
    @{ src = "user_data/data/binance/"; dst = "user_data/data/binance/" ; desc = "OHLCV feathers (~500MB)" }
    @{ src = "user_data/data/halving_cycle.feather"; dst = "user_data/data/"; desc = "halving phases" }
    @{ src = "user_data/data/macro_signals.feather"; dst = "user_data/data/"; desc = "macro signals (DXY/VIX/SPY)" }
    @{ src = "user_data/data/historical_analogs_v2.feather"; dst = "user_data/data/"; desc = "AnalogV2 KNN signals" }
    @{ src = "user_data/data/historical_analogs_v2_oos.feather"; dst = "user_data/data/"; desc = "OOS validation results" }
    @{ src = "user_data/data/anomaly_flags.feather"; dst = "user_data/data/"; desc = "anomaly detection flags" }
    @{ src = "research/experiments/"; dst = "research/experiments/"; desc = "backtest archive (~3500 runs)" }
    @{ src = "research/comprehensive_backtest_results.json"; dst = "research/"; desc = "summary JSON" }
)

# Confirm before transferring large data
Write-Host "Will transfer:" -ForegroundColor Yellow
foreach ($i in $items) { Write-Host "  $($i.src) — $($i.desc)" }
Write-Host ""
$confirm = Read-Host "Proceed? (y/n)"
if ($confirm -ne "y") { Write-Host "Aborted."; exit 0 }

# Transfer
foreach ($item in $items) {
    Write-Host "`n>>> $($item.desc)" -ForegroundColor Cyan
    $src = "${SOURCE_USER}@${SOURCE_HOST}:${SOURCE_BASE}/$($item.src)"
    $dst = Join-Path $DEST_BASE $item.dst
    New-Item -ItemType Directory -Force -Path (Split-Path $dst -Parent) | Out-Null
    if ($item.src.EndsWith("/")) {
        # Directory — recursive
        scp -r $src $dst
    } else {
        scp $src $dst
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: $($item.src)" -ForegroundColor Red
    } else {
        Write-Host "OK" -ForegroundColor Green
    }
}

# Sync Claude Code conversation history + memory
Write-Host "`n>>> Claude Code session history" -ForegroundColor Cyan
$claudeDir = "$env:USERPROFILE\.claude\projects\d--pythone-trad-system"
$srcClaude = "${SOURCE_USER}@${SOURCE_HOST}:/c/Users/user/.claude/projects/d--pythone-trad-system/"
New-Item -ItemType Directory -Force -Path $claudeDir | Out-Null
scp -r $srcClaude/* $claudeDir/
if ($LASTEXITCODE -eq 0) {
    Write-Host "OK — Claude history + memory synced to $claudeDir" -ForegroundColor Green
}

Write-Host "`n=== Sync complete! ===" -ForegroundColor Green
Write-Host "Verify:"
Write-Host "  Get-ChildItem -Recurse user_data/data | Measure-Object -Property Length -Sum"
Write-Host "  Get-ChildItem research/experiments | Measure-Object"
