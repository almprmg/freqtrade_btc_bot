# setup_gpu.ps1 - One-shot setup for GPU machine (Windows + PowerShell)
# Run from the freqtrade_btc_bot directory after git clone.
#
# Usage: powershell -ExecutionPolicy Bypass -File GPU_HANDOFF/setup_gpu.ps1

$ErrorActionPreference = "Stop"
Write-Host "=== GPU Setup Script ===" -ForegroundColor Cyan
Write-Host ""

# Step 1: Verify GPU + CUDA
Write-Host "Step 1: Checking GPU..." -ForegroundColor Yellow
$nvSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if (-not $nvSmi) {
    Write-Host "ERROR: nvidia-smi not found. Install NVIDIA driver first." -ForegroundColor Red
    exit 1
}
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv
Write-Host ""

$nvccVer = $null
try { $nvccVer = (nvcc --version 2>&1 | Select-String "release").ToString() } catch {}
if ($nvccVer) {
    Write-Host "CUDA: $nvccVer" -ForegroundColor Green
} else {
    Write-Host "WARN: CUDA toolkit not found. PyTorch will still work via bundled CUDA." -ForegroundColor Yellow
}
Write-Host ""

# Step 2: Python venv
Write-Host "Step 2: Creating venv..." -ForegroundColor Yellow
if (-not (Test-Path ".venv")) {
    python -m venv .venv
} else {
    Write-Host "venv already exists, skipping." -ForegroundColor Gray
}
& .venv\Scripts\Activate.ps1
Write-Host "Python: $(python --version)" -ForegroundColor Green
Write-Host ""

# Step 3: Upgrade pip
Write-Host "Step 3: Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip --quiet

# Step 4: PyTorch with CUDA
Write-Host "Step 4: Installing PyTorch with CUDA 12.1..." -ForegroundColor Yellow
pip install --quiet torch torchvision --index-url https://download.pytorch.org/whl/cu121

# Verify CUDA available
# Note: take the LAST output line — a missing VC++ redist prints a benign
# warning to stdout that would otherwise pollute the comparison.
$cudaOk = (python -c "import torch; print(torch.cuda.is_available())" 2>$null | Select-Object -Last 1)
if ("$cudaOk".Trim() -ne "True") {
    Write-Host "ERROR: PyTorch installed but CUDA not available!" -ForegroundColor Red
    Write-Host "Run: python -c `"import torch; print(torch.version.cuda)`"" -ForegroundColor Yellow
    exit 1
}
$gpuName = (python -c "import torch; print(torch.cuda.get_device_name(0))" 2>$null | Select-Object -Last 1)
Write-Host "GPU recognized: $gpuName" -ForegroundColor Green
Write-Host ""

# Step 5: Core ML stack
Write-Host "Step 5: Installing ML dependencies..." -ForegroundColor Yellow
pip install --quiet `
    pandas pyarrow `
    scikit-learn `
    lightning `
    transformers `
    wandb `
    stable-baselines3 gymnasium `
    matplotlib seaborn plotly `
    talib-binary `
    yfinance

# Step 6: Freqtrade itself (for backtest validation)
Write-Host "Step 6: Installing freqtrade..." -ForegroundColor Yellow
pip install --quiet freqtrade

# Step 7: Project requirements
if (Test-Path "requirements.txt") {
    Write-Host "Step 7: Installing project requirements.txt..." -ForegroundColor Yellow
    pip install --quiet -r requirements.txt
}

if (Test-Path "pyproject.toml") {
    Write-Host "Step 7b: Installing project in editable mode..." -ForegroundColor Yellow
    pip install --quiet -e .
}

# Step 8: Verify all imports
Write-Host "Step 8: Verifying critical imports..." -ForegroundColor Yellow
$verify = @'
import sys
errors = []
for mod in ["torch", "pandas", "numpy", "sklearn", "lightning", "talib"]:
    try:
        __import__(mod)
        print(f"  OK  {mod}")
    except ImportError as e:
        print(f"  FAIL {mod}: {e}")
        errors.append(mod)
import torch
print(f"PyTorch: {torch.__version__}")
print(f"CUDA: {torch.cuda.is_available()}, GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none'}")
if torch.cuda.is_available():
    print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
sys.exit(1 if errors else 0)
'@
python -c $verify

if ($LASTEXITCODE -ne 0) {
    Write-Host "Some imports failed - review above." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=== Setup complete! ===" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Copy data from CPU machine (see GPU_HANDOFF/sync_data.ps1)"
Write-Host "  2. Read GPU_HANDOFF/CONTEXT_FOR_GPU_AI.md for project context"
Write-Host "  3. Start training: python GPU_HANDOFF/dl_train_lstm.py --epochs 50"
