"""sweep.py — Architecture / capacity / loss / sequence sweep for the daily model.

The user's goal is training AI models on the GPU. This runs a one-factor-at-a-time
grid (vs a sensible baseline) over BTC+ETH 1d via walk-forward and reports the
best configuration. Each cell is a full 5-fold walk-forward of dl_train_lstm.py.

USAGE:  python GPU_HANDOFF/sweep.py
Output: research/reports/LSTM_SWEEP.md + research/dl_models/sweep_results.json
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = "GPU_HANDOFF/dl_train_lstm.py"
COINS = ["BTC", "ETH"]
MEAN_RE = re.compile(r"Mean corr \(at best ckpt\):\s*([+-][0-9.]+)\s*\+/-\s*([0-9.]+)")

BASE = {"arch": "lstm", "hidden": 64, "layers": 2, "dropout": 0.3, "seq": 60, "loss": "corr"}

# One-factor-at-a-time variations vs BASE.
CONFIGS = [
    {"label": "baseline (lstm h64 l2 d0.3 s60 corr)"},
    {"label": "arch=gru", "arch": "gru"},
    {"label": "arch=transformer", "arch": "transformer"},
    {"label": "loss=mse", "loss": "mse"},
    {"label": "loss=combo", "loss": "combo"},
    {"label": "hidden=128", "hidden": 128},
    {"label": "layers=1", "layers": 1},
    {"label": "layers=3", "layers": 3},
    {"label": "seq=30", "seq": 30},
    {"label": "seq=90", "seq": 90},
    {"label": "dropout=0.5", "dropout": 0.5},
]


def run_one(coin, cfg):
    c = {**BASE, **cfg}
    cmd = [sys.executable, SCRIPT, "--coin", coin, "--timeframe", "1d",
           "--mode", "walkforward", "--folds", "5", "--epochs", "80", "--batch", "256",
           "--loss", c["loss"], "--arch", c["arch"], "--hidden", str(c["hidden"]),
           "--layers", str(c["layers"]), "--dropout", str(c["dropout"]), "--seq", str(c["seq"])]
    out = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True).stdout
    m = MEAN_RE.search(out)
    return (float(m.group(1)), float(m.group(2))) if m else (float("nan"), float("nan"))


def main():
    results = []
    for cfg in CONFIGS:
        row = {"label": cfg["label"], "config": {**BASE, **{k: v for k, v in cfg.items() if k != "label"}}}
        per_coin = {}
        for coin in COINS:
            mean, std = run_one(coin, cfg)
            per_coin[coin] = {"mean": mean, "std": std}
            print(f"  {cfg['label']:<40} {coin}: {mean:+.4f} +/- {std:.4f}", flush=True)
        avg = sum(v["mean"] for v in per_coin.values()) / len(per_coin)
        row["per_coin"] = per_coin
        row["avg_mean"] = avg
        results.append(row)
        print(f"  -> {cfg['label']:<40} AVG {avg:+.4f}\n", flush=True)

    results.sort(key=lambda r: r["avg_mean"], reverse=True)

    (REPO / "research" / "dl_models" / "sweep_results.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8")

    lines = ["# LSTM Daily Model — Architecture / Capacity / Loss Sweep\n",
             "Walk-forward (5 folds) on BTC+ETH 1d. One-factor-at-a-time vs baseline.",
             "Ranked by avg of BTC & ETH mean walk-forward correlation.\n",
             "| Rank | Config | BTC | ETH | **Avg** |",
             "|---|---|---|---|---|"]
    for i, r in enumerate(results, 1):
        b, e = r["per_coin"]["BTC"], r["per_coin"]["ETH"]
        lines.append(f"| {i} | {r['label']} | {b['mean']:+.3f}±{b['std']:.2f} | "
                     f"{e['mean']:+.3f}±{e['std']:.2f} | **{r['avg_mean']:+.3f}** |")
    best = results[0]
    lines += ["", f"**Best:** `{best['label']}` → avg corr **{best['avg_mean']:+.3f}** "
              f"(baseline was {next(r['avg_mean'] for r in results if 'baseline' in r['label']):+.3f}).",
              "\nKNN baseline +0.06 · single-coin target was +0.15."]
    (REPO / "research" / "reports" / "LSTM_SWEEP.md").write_text(
        "\n".join(lines), encoding="utf-8")
    print("\n=== SWEEP DONE ===")
    print("\n".join(lines[3:]))


if __name__ == "__main__":
    main()
