"""comprehensive_backtest.py — Run all strategies on 9 years, save everything.

For each strategy:
  - 9-year yearly backtest (2018-2026 Q12)
  - Save trades.csv, metadata.json per year
  - Aggregate stats per strategy
"""
from __future__ import annotations

import json
import subprocess
import sys
import os
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

YEARS = ["20180101-20190101", "20190101-20200101", "20200101-20210101",
         "20210101-20220101", "20220101-20230101", "20230101-20240101",
         "20240101-20250101", "20250101-20260101", "20260101-20260601"]

# (config_name, strategy_class, label, env_vars, coin)
STRATEGIES = [
    # === DEPLOYED on trad-server ===
    ("config.ai_shield.json",         "BtcAiShieldStrategy",         "AI Shield V1 (#97)",        {}, "BTC"),
    ("config.triple.json",            "BtcTripleRegimeStrategy",     "Triple Regime BTC (#99)",   {"TR_MODE": "TR_STRICT"}, "BTC"),
    ("config.ai_shield_v2.json",      "BtcAiShieldV2Strategy",       "AI Shield V2 (#99)",        {}, "BTC"),
    ("config.calendar.json",          "BtcCalendarShieldStrategy",   "Calendar BTC (#100)",       {}, "BTC"),
    ("config.shield-ETH.json",        "BtcRegimeShieldStrategy",     "ETH Pure Shield (#101)",    {}, "ETH"),
    ("config.volshield-SOL.json",     "SolVolShieldStrategy",        "SOL VolShield (#102)",      {}, "SOL"),
    ("config.calendar-ETH.json",      "BtcCalendarShieldStrategy",   "Calendar ETH (#105)",       {}, "ETH"),
    ("config.calendar-BNB.json",      "BtcCalendarShieldStrategy",   "Calendar BNB (#106)",       {}, "BNB"),
    ("config.calendar-XRP.json",      "BtcCalendarShieldStrategy",   "Calendar XRP (#107)",       {}, "XRP"),
    ("config.macrov2.json",           "BtcMacroV2Strategy",          "Macro V2 BTC (#108)",       {"MV_W_MACRO":"0.20","MV_W_SPY":"0.10","MV_EXIT_THR":"-0.70","MV_MODE":"tilt"}, "BTC"),
    # === STAR (not yet deployed) ===
    ("config.analogv2-ETH.json",      "BtcAnalogV2Strategy",         "AnalogV2 ETH STAR",         {}, "ETH"),
    ("config.analogv2.json",          "BtcAnalogV2Strategy",         "AnalogV2 BTC",              {}, "BTC"),
    # === RECENT experiments ===
    ("config.analog.json",            "BtcAnalogShieldStrategy",     "AnalogShield V1 BTC",       {}, "BTC"),
    ("config.macro.json",             "BtcMacroShieldStrategy",      "Macro Shield V1 BTC",       {}, "BTC"),
    ("config.calv2.json",             "BtcCalendarV2Strategy",       "Calendar V2 BTC",           {"CAL_W_JUL":"-0.05","CAL_W_JAN":"0.10"}, "BTC"),
    ("config.bounce.json",            "BtcBounceScalperStrategy",    "Bounce Scalper 1d",         {}, "BTC"),
    ("config.bouncev2.json",          "BtcBounceV2Strategy",         "BounceV2 (MACD div)",       {}, "BTC"),
    ("config.swing.json",             "BtcSwingDcaStrategy",         "Swing DCA V1",              {}, "BTC"),
    ("config.swingv2.json",           "BtcSwingV2Strategy",          "SwingV2 (HH/HL)",           {}, "BTC"),
    ("config.breakout.json",          "BtcBreakoutBossStrategy",     "Breakout Boss",             {}, "BTC"),
    ("config.quantum.json",           "QuantumAiShieldStrategy",     "Quantum AI",                {}, "BTC"),
]


def run_backtest(cfg, strategy, label, env_overrides, year_range, mode):
    env = os.environ.copy()
    env.update({k: str(v) for k, v in env_overrides.items()})
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [
        sys.executable, "-m", "research.ai.logged_backtest",
        "--config", cfg,
        "--strategy", strategy,
        "--timerange", year_range,
        "--mode", mode,
        "--notes", f"COMPRE_{label}",
    ]
    try:
        p = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, text=True, timeout=180)
        # parse the summary line
        for line in p.stdout.splitlines()[-10:]:
            if "ROI:" in line and "trades:" in line:
                try:
                    roi = float(line.split("ROI:")[1].split("%")[0].strip())
                    n = int(line.split("trades:")[1].split(",")[0].strip())
                    dd = float(line.split("max_dd:")[1].split("%")[0].strip())
                    return {"roi": roi, "n": n, "dd": dd, "ok": True}
                except: pass
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": False, "error": "no_parse"}


def main():
    print(f"Total strategies: {len(STRATEGIES)}")
    print(f"Total years: {len(YEARS)}")
    print(f"Total backtests: {len(STRATEGIES) * len(YEARS)}")
    print()

    all_results = {}
    start = time.time()
    total_runs = len(STRATEGIES) * len(YEARS)
    run_i = 0

    for cfg, strategy, label, env_vars, coin in STRATEGIES:
        if not (REPO / cfg).exists():
            print(f"SKIP {label}: config {cfg} missing")
            continue
        all_results[label] = {"coin": coin, "years": {}}
        for yr_range in YEARS:
            yr = yr_range[:4]
            run_i += 1
            mode = f"CBT_{label.replace(' ', '_').replace('(', '').replace(')', '').replace('#', 'n').replace('+', 'p').replace('/', '_')[:30]}_{yr}"
            result = run_backtest(cfg, strategy, label, env_vars, yr_range, mode)
            all_results[label]["years"][yr] = result
            elapsed = time.time() - start
            avg = elapsed / run_i
            eta = avg * (total_runs - run_i)
            print(f"[{run_i:>3}/{total_runs}] {label[:30]:<30} {yr} {result}  (ETA {eta/60:.1f}m)")

    # Save raw results
    out = REPO / "research" / "comprehensive_backtest_results.json"
    out.write_text(json.dumps(all_results, indent=2), encoding="utf-8")
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
