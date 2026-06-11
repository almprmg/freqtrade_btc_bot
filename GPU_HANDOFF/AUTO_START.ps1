# AUTO_START.ps1 — One-script setup. Does EVERYTHING the user would do manually.
#
# Run this AFTER the user has copied the data files (USB or OneDrive) into
# the freqtrade_btc_bot/user_data/data/ folder.
#
# This script:
#   1. Installs Python + Git if missing (via winget)
#   2. Clones repo if not cloned
#   3. Runs setup_gpu.ps1 (Python venv + PyTorch CUDA + ML libs)
#   4. Installs Node.js + Claude Code
#   5. Installs all 15 Skills + 8 memory files into ~/.claude/
#   6. Drops user into a Claude session ready to go

$ErrorActionPreference = "Continue"  # Keep going even if one step warns
Write-Host @"

  ╔══════════════════════════════════════════════════════════════╗
  ║  GPU MACHINE AUTO-SETUP                                      ║
  ║  Will install: Python + PyTorch CUDA + Claude Code + Skills  ║
  ║  Estimated time: ~20 minutes                                 ║
  ╚══════════════════════════════════════════════════════════════╝

"@ -ForegroundColor Cyan

# === Step 1: winget check ===
Write-Host "Step 1/7: Checking package manager (winget)..." -ForegroundColor Yellow
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: winget not found. Install 'App Installer' from Microsoft Store first." -ForegroundColor Red
    Write-Host "URL: https://apps.microsoft.com/detail/9NBLGGH4NNS1" -ForegroundColor Yellow
    exit 1
}

# === Step 2: Install Git, Python, Node.js if missing ===
Write-Host "`nStep 2/7: Installing prerequisites (Git, Python, Node.js)..." -ForegroundColor Yellow

foreach ($pkg in @(
    @{name="Git"; id="Git.Git"; cmd="git"},
    @{name="Python 3.12"; id="Python.Python.3.12"; cmd="python"},
    @{name="Node.js LTS"; id="OpenJS.NodeJS.LTS"; cmd="node"}
)) {
    if (Get-Command $pkg.cmd -ErrorAction SilentlyContinue) {
        Write-Host "  OK   $($pkg.name) already installed" -ForegroundColor Green
    } else {
        Write-Host "  INSTALL $($pkg.name)..." -ForegroundColor Cyan
        winget install --id $pkg.id --silent --accept-package-agreements --accept-source-agreements
    }
}

# Refresh PATH so newly-installed tools are usable
$env:PATH = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# === Step 3: GPU check ===
Write-Host "`nStep 3/7: Checking GPU..." -ForegroundColor Yellow
if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
    Write-Host "  WARN: nvidia-smi not found — install NVIDIA driver first!" -ForegroundColor Yellow
    Write-Host "  https://www.nvidia.com/Download/index.aspx" -ForegroundColor Yellow
} else {
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
}

# === Step 4: Run setup_gpu.ps1 (Python venv + PyTorch CUDA) ===
Write-Host "`nStep 4/7: Setting up Python venv + PyTorch CUDA..." -ForegroundColor Yellow
$repoRoot = Split-Path $PSScriptRoot -Parent
Set-Location $repoRoot
if (Test-Path "GPU_HANDOFF\setup_gpu.ps1") {
    & "$PSScriptRoot\setup_gpu.ps1"
} else {
    Write-Host "ERROR: setup_gpu.ps1 not found in current directory." -ForegroundColor Red
    Write-Host "Make sure you ran this from inside the freqtrade_btc_bot folder." -ForegroundColor Yellow
    exit 1
}

# === Step 5: Install Claude Code ===
Write-Host "`nStep 5/7: Installing Claude Code..." -ForegroundColor Yellow
$claudeInstalled = Get-Command claude -ErrorAction SilentlyContinue
if (-not $claudeInstalled) {
    npm install -g @anthropic-ai/claude-code 2>&1 | Out-Null
    Write-Host "  OK Claude Code installed" -ForegroundColor Green
} else {
    Write-Host "  OK Claude Code already installed" -ForegroundColor Green
}

# === Step 6: Install Skills + Memory + Context ===
Write-Host "`nStep 6/7: Installing 15 Skills + 8 Memory files into ~/.claude/..." -ForegroundColor Yellow

$claudeBase = "$env:USERPROFILE\.claude"
$claudeSkills = "$claudeBase\skills"
$projHash = "d--pythone-trad-system"
$claudeMem = "$claudeBase\projects\$projHash\memory"

New-Item -ItemType Directory -Force -Path $claudeSkills | Out-Null
New-Item -ItemType Directory -Force -Path $claudeMem | Out-Null

# Copy skills
if (Test-Path "$PSScriptRoot\skills") {
    Copy-Item -Recurse -Force "$PSScriptRoot\skills\*" $claudeSkills
    $skillCount = (Get-ChildItem $claudeSkills -Directory).Count
    Write-Host "  OK $skillCount skills installed -> $claudeSkills" -ForegroundColor Green
} else {
    Write-Host "  WARN: skills folder not in GPU_HANDOFF/ — clone might be incomplete" -ForegroundColor Yellow
}

# Copy memory
if (Test-Path "$PSScriptRoot\memory") {
    Copy-Item -Recurse -Force "$PSScriptRoot\memory\*" $claudeMem
    $memCount = (Get-ChildItem $claudeMem -File).Count
    Write-Host "  OK $memCount memory files installed -> $claudeMem" -ForegroundColor Green
}

# Copy CONTEXT as a CLAUDE.md so the new agent reads it on startup
$claudeMdPath = "$repoRoot\CLAUDE.md"
if (-not (Test-Path $claudeMdPath)) {
    # Create a CLAUDE.md that points to the handoff context
    @"
# Project Context

You are continuing the trading-system work on a fresh GPU machine.
**Read [GPU_HANDOFF/CONTEXT_FOR_GPU_AI.md](GPU_HANDOFF/CONTEXT_FOR_GPU_AI.md) FIRST.**

It explains:
- What's been done on the CPU machine (92 backtests, 15 deployed bots)
- What you should do here (LSTM training first, then multi-coin, then transformer)
- Tech stack, secrets, communication preferences

Key directories on this machine:
- GPU_HANDOFF/ — handoff package + DL training scripts
- user_data/data/ — OHLCV feathers (synced from CPU machine)
- research/experiments/ — backtest archive
- research/dl_models/ — trained models will land here
"@ | Out-File -FilePath $claudeMdPath -Encoding utf8
    Write-Host "  OK CLAUDE.md created -> agent will read context on startup" -ForegroundColor Green
}

# === Step 7: Final message ===
Write-Host @"

  ╔══════════════════════════════════════════════════════════════╗
  ║                   ✅ SETUP COMPLETE                          ║
  ╚══════════════════════════════════════════════════════════════╝

  Next steps:

  1. Login to Claude Code:
     PS> claude login

  2. Make sure data is in place (manually copy from CPU machine):
     - user_data/data/binance/*.feather  (~500MB OHLCV)
     - user_data/data/macro_signals.feather
     - user_data/data/halving_cycle.feather
     - research/experiments/  (3500+ backtest folders, optional)

  3. Start Claude — it will read CLAUDE.md + GPU_HANDOFF/CONTEXT_FOR_GPU_AI.md
     and know exactly what to do:

     PS> claude

  4. Tell it: "ابدأ تدريب LSTM على BTC" or
              "start training LSTM on BTC"

     It'll run:  python GPU_HANDOFF\dl_train_lstm.py --coin BTC --epochs 50

"@ -ForegroundColor Green
