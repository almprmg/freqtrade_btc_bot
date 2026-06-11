"""run_pipeline.py — End-to-end strategy development pipeline.

Orchestrates all 5 phases:
  1. Hypothesis (you state it)
  2. Build (from template)
  3. Backtest (6-window yearly grid)
  4. Adversarial (3-window gate)
  5. Deploy (if PASS/WARN)

Usage:
  python -m strategy_lab.run_pipeline \
    --coin SOL \
    --template vol_shield \
    --class-name SolMyShield \
    --hypothesis "Volatility-aware filters should reduce 2025 chop drawdown" \
    --wallet 3000

Or interactively:
  python -m strategy_lab.run_pipeline --interactive

NOTE: This file is the spec. It calls existing tools in the repo:
  research/ai/logged_backtest.py
  research/ai/adversarial_validator.py

The skill's value is the WORKFLOW, not new tools. Use the existing
ones in the freqtrade_btc_bot repo.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


# Match these to the freqtrade_btc_bot layout
REPO = Path("d:/pythone/freqtrade_btc_bot")
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

YEARLY_WINDOWS = [
    ("2021",    "20210101-20220101"),
    ("2022",    "20220101-20230101"),
    ("2023",    "20230101-20240101"),
    ("2024",    "20240101-20250101"),
    ("2025",    "20250101-20260101"),
    ("2026Q12", "20260101-20260601"),
]


def render_template(template_name: str, output_path: Path, **subs):
    """Simple {{ var }} substitution from a template."""
    tmpl = (TEMPLATES_DIR / template_name).read_text(encoding="utf-8")
    for k, v in subs.items():
        tmpl = tmpl.replace("{{ " + k + " }}", str(v))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(tmpl, encoding="utf-8")
    print(f"  wrote: {output_path}")


def phase_1_hypothesis(hypothesis: str):
    print(f"\n=== Phase 1 — Hypothesis ===")
    if not hypothesis or len(hypothesis) < 20:
        print("  ERROR: hypothesis too short. State 'X improves over Y on Z because W'")
        sys.exit(1)
    print(f"  Hypothesis: {hypothesis}")

    print("\n  Pre-mortem question: 'What would failure look like?'")
    print("  Spend 60 seconds on this before continuing.")
    input("  Press Enter when ready... ")


def phase_2_build(coin: str, template: str, class_name: str, hypothesis: str,
                  slug: str, wallet: int):
    print(f"\n=== Phase 2 — Build ===")

    n_confirm = {"BTC": 3, "ETH": 3, "BNB": 3, "DOGE": 4, "ADA": 3,
                 "SOL": 5, "AVAX": 5}.get(coin, 3)
    tag = slug.replace("_", "-")

    common = {
        "ClassName": class_name,
        "COIN": coin,
        "hypothesis": hypothesis,
        "n_confirm": n_confirm,
        "tag": tag,
        "slug": slug,
        "bot_name": slug,
    }

    strategy_file = REPO / "user_data" / "strategies" / f"{slug}_strategy.py"
    config_file = REPO / f"config.{slug}.json"

    render_template(f"strategy_{template}.py.tmpl", strategy_file, **common)
    render_template("config.json.tmpl", config_file, **common)
    print(f"  Files created. REVIEW them before continuing.")
    print(f"  Strategy: {strategy_file}")
    print(f"  Config:   {config_file}")
    input("  Press Enter after review... ")


def phase_3_backtest(slug: str, class_name: str):
    print(f"\n=== Phase 3 — Backtest (6 yearly windows) ===")
    rois = []
    for tag, tr in YEARLY_WINDOWS:
        cmd = [
            sys.executable, "-m", "research.ai.logged_backtest",
            "--config", f"config.{slug}.json",
            "--strategy", f"{class_name}Strategy",
            "--timerange", tr,
            "--mode", f"Y_{tag}",
            "--notes", f"strategy-lab pipeline for {slug}",
        ]
        print(f"  Running {tag}...")
        p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
        roi = 0.0
        for line in p.stdout.splitlines()[-25:]:
            if "ROI:" in line:
                try:
                    roi = float(line.split("ROI:")[1].split("%")[0].strip())
                except ValueError:
                    pass
                print(f"    {line.strip()}")
        rois.append(roi)

    compound = 1.0
    for r in rois:
        compound *= (1 + r/100)
    annual = compound ** (1/5) - 1
    print(f"\n  Yearly ROIs: {rois}")
    print(f"  5y compound: ${10000*compound:,.0f}")
    print(f"  Annual: {annual*100:.1f}%/yr")
    return rois, annual


def phase_4_adversarial(slug: str, class_name: str):
    print(f"\n=== Phase 4 — Adversarial Validation (GATE) ===")
    cmd = [
        sys.executable, "-m", "research.ai.adversarial_validator",
        "--strategy", f"{class_name}Strategy",
        "--config", f"config.{slug}.json",
        "--name", slug,
        "--skip-baselines",
    ]
    p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    verdict = "UNKNOWN"
    for line in p.stdout.splitlines()[-10:]:
        print(f"  {line.rstrip()}")
        for v in ["PASS", "WARN", "FAIL", "CATASTROPHIC"]:
            if v in line and slug in line:
                verdict = v
    return verdict


def phase_5_deploy(slug: str, class_name: str, coin: str, hypothesis: str,
                   annual: float, verdict: str, wallet: int):
    print(f"\n=== Phase 5 — Deploy ===")
    if verdict not in ("PASS", "WARN"):
        print(f"  Verdict is {verdict}. NOT DEPLOYING.")
        print(f"  Document this rejection in C:/Users/user/.claude/skills/strategy-lab/examples/")
        return

    if verdict == "WARN":
        wallet = min(wallet, 2000)
        print(f"  WARN verdict — reducing wallet to ${wallet}")

    print(f"  Generating deployment artifacts for sub ${wallet} wallet...")

    docker_file = REPO / f"docker-compose.{slug}.yml"
    sql_file = Path("d:/tmp") / f"{slug}_insert.sql"

    common = {
        "ClassName": class_name,
        "COIN": coin,
        "hypothesis": hypothesis,
        "hypothesis_short": hypothesis[:80],
        "backtest_summary": f"{annual*100:.1f}%/yr 5y",
        "adversarial_verdict": verdict,
        "slug": slug,
        "bot_name": slug,
        "SLUG_UPPER": slug.upper(),
        "display_name": f"{coin} {class_name}",
        "description": f"{hypothesis} | Backtest {annual*100:.1f}%/yr | Adversarial {verdict}",
        "strategy_type": slug,
        "wallet_usd": wallet,
    }

    render_template("docker-compose.yml.tmpl", docker_file, **common)
    render_template("insert_sub.sql.tmpl", sql_file, **common)

    print(f"\n  Artifacts ready:")
    print(f"    SQL:    {sql_file}")
    print(f"    Compose: {docker_file}")
    print(f"\n  Next steps (manual for safety):")
    print(f"    1. scp + docker cp the SQL to trad-server")
    print(f"    2. docker exec trad_pg psql -f /tmp/{slug}_insert.sql")
    print(f"    3. Capture the sub_id, write .env.{slug}, chmod 600")
    print(f"    4. docker compose -f docker-compose.{slug}.yml --env-file .env.{slug} up -d")
    print(f"    5. Verify both bot+bridge containers Up")
    print(f"\n  Or use: bash scripts/deploy_bot.sh {slug}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--coin", required=True, help="BTC|ETH|SOL|BNB|DOGE|ADA|AVAX")
    p.add_argument("--template", required=True,
                   choices=["pure_shield", "calendar", "vol_shield"],
                   help="Which template to use")
    p.add_argument("--class-name", required=True, help="e.g. SolMyShield")
    p.add_argument("--hypothesis", required=True,
                   help="'X improves over Y on Z because W'")
    p.add_argument("--wallet", type=int, default=3000)
    p.add_argument("--slug", default=None, help="defaults to class_name.lower()")
    args = p.parse_args()

    slug = args.slug or args.class_name.lower()

    phase_1_hypothesis(args.hypothesis)
    phase_2_build(args.coin, args.template, args.class_name, args.hypothesis,
                  slug, args.wallet)
    rois, annual = phase_3_backtest(slug, args.class_name)
    verdict = phase_4_adversarial(slug, args.class_name)
    phase_5_deploy(slug, args.class_name, args.coin, args.hypothesis,
                   annual, verdict, args.wallet)


if __name__ == "__main__":
    main()
