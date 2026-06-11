---
name: data-engineer
description: Crypto data pipeline maintainer. Keeps OHLCV daily candles, anomaly_flags, halving_cycle, FGI sentiment, and per-coin auxiliary feathers FRESH and consistent. Use when user asks "refresh data", "update OHLCV", "data is stale", "new coin onboarding", "anomaly model retrain", "fetch FGI", or any data-pipeline concern. Without this skill, backtests progressively decouple from live behavior as data ages.
---

# Data Engineer — Crypto Data Pipeline Maintainer

The data freshness skill. The strategies are only as good as the data they're tested on.

For strategy DESIGN, use `strategy-architect`. For backtesting, use `bot-builder`. For audit, use `strategy-researcher`.

## When to invoke

- "Refresh OHLCV data"
- "Data is stale"
- "Update anomaly flags"
- "FGI history is outdated"
- "Onboard new coin to data pipeline"
- "Retrain anomaly detector"
- "Update halving phase data"
- "Check data integrity"

## Data assets managed

### 1. OHLCV daily candles (per coin)
- Location: `d:/pythone/freqtrade_btc_bot/user_data/data/binance/<COIN>_USDT-1d.feather`
- Updates: daily (freqtrade builtin download-data)
- Source: Binance public API
- Coins tracked: BTC, ETH, SOL, BNB, AVAX, DOGE, ADA

### 2. Anomaly flags (per coin)
- Location: `user_data/data/anomaly_flags.feather`
- Schema: date, coin, is_anomaly (0/1), feature vector summary
- Built by: `research/ai/anomaly_detector.py` (Isolation Forest, contamination=0.025)
- Train: 2019-2023
- Updates: monthly retrain recommended

### 3. Halving cycle bias (BTC-only)
- Location: `user_data/data/halving_cycle.feather`
- Schema: date, cycle_bias (-1..+1), phase (ACCUMULATION/EARLY_BULL/PARABOLIC/DISTRIBUTION/BEAR/REACCUMULATION)
- Built by: `research/ai/halving_cycle_predictor.py` (rule-based)
- Updates: extends automatically as new dates pass (no retraining needed)

### 4. Fear & Greed Index history
- Location: `user_data/data/fgi.feather` + `user_data/data/fgi_signal.feather`
- Source: alternative.me public API (free, historical)
- Built by: `research/ai/sentiment_test.py` (fetch) + `research/ai/build_fgi_feature.py` (tilt mapping)
- Updates: daily

### 5. Asset cycles (per-coin price-derived)
- Location: `user_data/data/asset_cycles.feather`
- Built by: `research/ai/compute_asset_cycles.py`
- Status: tested in Idea F — FAILED to add value over coin-specific strategies. Kept for reference.

## Refresh procedures

### Daily refresh (OHLCV + FGI)
```bash
cd d:/pythone/freqtrade_btc_bot

# 1. Update OHLCV for each coin (freqtrade builtin)
./.venv/Scripts/python.exe -m freqtrade download-data \
  --exchange binance \
  --timeframes 1d \
  --pairs BTC/USDT ETH/USDT SOL/USDT BNB/USDT AVAX/USDT DOGE/USDT ADA/USDT \
  --timerange 20180101- \
  --userdir user_data

# 2. Refresh FGI
./.venv/Scripts/python.exe -c "
from research.ai.sentiment_test import fetch_fgi
df = fetch_fgi()
print(f'FGI rows: {len(df)}, latest: {df[\"date\"].max()}')"

./.venv/Scripts/python.exe -m research.ai.build_fgi_feature
```

### Weekly refresh (anomaly flags, calendar features)
```bash
# Anomaly model — retrain monthly OR when adding new coin
./.venv/Scripts/python.exe -m research.ai.anomaly_detector --train 20190101-20240101 --apply-from 20240101

# Calendar features — recompute when new data added
./.venv/Scripts/python.exe -m research.ai.calendar_analyzer
```

### New-coin onboarding (rare)
When adding a coin to the supported set:

1. Add to `COINS` constant in:
   - `research/ai/anomaly_detector.py`
   - `research/ai/compute_asset_cycles.py`
   - `strategy-architect/knowledge/coin_profiles.md`

2. Download historical data:
```bash
./.venv/Scripts/python.exe -m freqtrade download-data \
  --exchange binance --timeframes 1d \
  --pairs <NEW_COIN>/USDT --timerange 20180101-
```

3. Run anomaly detector to add the new coin's flags:
```bash
./.venv/Scripts/python.exe -m research.ai.anomaly_detector --retrain-all
```

4. Compute vol profile:
```python
import pandas as pd
df = pd.read_feather(f"user_data/data/binance/{COIN}_USDT-1d.feather")
ann_vol = df["close"].pct_change().std() * (365 ** 0.5) * 100
print(f"{COIN} ann vol: {ann_vol:.0f}%")
```

5. Update `coin_profiles.md` with the new entry.

6. THEN, only then, ready for `bot-builder` to start using the coin.

## Data integrity checks

Run these monthly or after any pipeline change:

### Check 1: No gaps in OHLCV
```python
df = pd.read_feather(f"user_data/data/binance/{COIN}_USDT-1d.feather")
df["date"] = pd.to_datetime(df["date"], utc=True)
df = df.sort_values("date").reset_index(drop=True)
expected_dates = pd.date_range(df["date"].min(), df["date"].max(), freq="D", tz="UTC")
gaps = set(expected_dates) - set(df["date"])
print(f"{COIN}: {len(gaps)} missing days" if gaps else f"{COIN}: complete")
```

### Check 2: Anomaly coverage matches coin set
```python
anom = pd.read_feather("user_data/data/anomaly_flags.feather")
coins_in_anom = anom["coin"].unique() if "coin" in anom.columns else []
expected = {"BTC", "ETH", "SOL", "BNB", "AVAX", "DOGE", "ADA"}
missing = expected - set(coins_in_anom)
if missing:
    print(f"⚠️ anomaly model missing coins: {missing}")
```

### Check 3: FGI freshness
```python
fgi = pd.read_feather("user_data/data/fgi.feather")
latest = fgi["date"].max()
age_days = (pd.Timestamp.now(tz="UTC") - latest).days
if age_days > 7:
    print(f"⚠️ FGI {age_days} days stale")
```

### Check 4: Halving cycle date coverage
```python
hc = pd.read_feather("user_data/data/halving_cycle.feather")
latest = hc.index.max() if hc.index.name == "date" else hc["date"].max()
if (pd.Timestamp.now(tz="UTC") - latest).days > 0:
    print(f"⚠️ halving cycle doesn't cover today — regenerate")
```

## Schedule automation

Run on trad-server via cron (these run NOT on the laptop, since data goes to docker volumes):

```cron
# Daily OHLCV + FGI refresh at 00:30 UTC
30 0 * * * /srv/trad/pythone/freqtrade_btc_bot/scripts/refresh_data_daily.sh

# Weekly anomaly retrain (Sundays 01:00 UTC)
0 1 * * 0 /srv/trad/pythone/freqtrade_btc_bot/scripts/refresh_anomaly_weekly.sh

# Monthly: full integrity check + report
0 2 1 * * /srv/trad/pythone/freqtrade_btc_bot/scripts/data_integrity_check.sh
```

This skill's `schedules/` folder contains these scripts as templates. Install via:
```bash
scp schedules/refresh_data_daily.sh trad-server:/srv/trad/pythone/freqtrade_btc_bot/scripts/
ssh trad-server 'chmod +x /srv/trad/.../scripts/refresh_data_daily.sh && (crontab -l; echo "30 0 * * * /srv/...") | crontab -'
```

## Failure modes & recovery

| Failure | Symptom | Recovery |
|---|---|---|
| Binance rate-limited | download-data hangs | Reduce parallelism, retry |
| Disk full | feather write fails | Clean old backtest result zips |
| FGI API down | alternative.me returns 5xx | Use cached + log warning |
| Anomaly retrain crash | OOM on large dataset | Train on subset, or use sampling |
| Date parser issue | utc conversion fails | Check timezone explicit in all reads |

## Data versioning

For reproducible backtests, keep snapshots:

```bash
# Tag current data state before major experiments
cd user_data/data
tar -czf snapshots/data-$(date +%Y%m%d).tar.gz binance/ anomaly_flags.feather halving_cycle.feather fgi*.feather
```

Then if a backtest produces a wildly different result, you can re-test against the OLD snapshot to isolate data-vs-code changes.

## What this skill does NOT do

- **Build strategies** — that's `bot-builder`
- **Test strategies** — that's `bot-builder` (logged_backtest wrapper)
- **Decide if data is "good enough"** — that's user judgment
- **Migrate exchanges** — code change, not data
- **Tune anomaly contamination** — that's strategy design (consult architect)

## Pre-deployment data check

Before deploying ANY new bot, this skill should verify (auto-called by bot-builder):

- [ ] OHLCV data is < 24h old
- [ ] Anomaly flags include the target coin
- [ ] FGI data is < 24h old (if strategy uses sentiment)
- [ ] No gaps in last 30 days of OHLCV
- [ ] Halving cycle data covers today (BTC strategies)

If any fail, BUILDER should refuse to deploy until DATA-ENGINEER fixes.
