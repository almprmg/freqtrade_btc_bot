# BTC/USDT Regime-Aware Bot — Freqtrade

A Binance **Spot-only** bot for `BTC/USDT` on a 4-hour primary timeframe.
The bot classifies the market on every closed 4h candle and routes to one
of two strategies:

| Regime    | Detection                                       | Strategy          |
|-----------|-------------------------------------------------|-------------------|
| TRENDING  | `ADX(14) > 25` **and** `ATR(14) > ATR_AVG(20)`  | Trend Pullback    |
| RANGING   | `ADX(14) < 20` **and** `ATR < ATR_AVG × 1.1`    | Mean Reversion    |
| NEUTRAL   | otherwise                                       | hold; no entries  |

A **3-bar whipsaw guard** stops single-bar flips from toggling strategies.

All entries / exits are LIMIT (Maker rebate). Position size is per-tag:
**15%** of wallet for mean-reversion, **20%** for trend-pullback. Max 3
open trades. Daily/monthly drawdown kill-switches at -5% / -15%.

## Layout

```
freqtrade_btc_bot/
├── config.json                  # LIVE config (dry_run=false)
├── config.dryrun.json           # DRY-RUN config (dry_run=true, 10k virtual wallet)
├── backtest.sh                  # download + lookahead + recursive + backtest
├── requirements.txt
├── conftest.py                  # makes user_data/ importable from pytest
├── user_data/
│   └── strategies/
│       ├── regime_detector.py        # RegimeDetector (no Freqtrade dep — unit-testable)
│       └── btc_regime_strategy.py    # IStrategy: MR + Trend Pullback, MTF, Maker pricing
└── tests/
    ├── test_regime_detector.py
    └── test_btc_regime_strategy.py
```

## Install

```bash
# 1. Python 3.10 venv (Freqtrade pins this)
python3.10 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate

# 2. Freqtrade + TA-Lib (TA-Lib needs system libs — see Freqtrade docs)
pip install -r requirements.txt

# 3. Sanity: freqtrade CLI works
freqtrade --version
```

If TA-Lib's wheel doesn't install, follow Freqtrade's install guide for
your OS (the system `libta-lib` package + `pip install TA-Lib`).

## Secrets — environment variables ONLY

Both configs intentionally leave secret fields **empty**. Freqtrade reads
overrides from environment variables using the `FREQTRADE__SECTION__KEY`
convention (double underscore). Export before running:

```bash
# Binance API keys (Spot account; trade-only permissions, no withdraw)
export FREQTRADE__EXCHANGE__KEY="<your_binance_api_key>"
export FREQTRADE__EXCHANGE__SECRET="<your_binance_api_secret>"

# Telegram (skip for backtest; required for live notifications)
export FREQTRADE__TELEGRAM__TOKEN="<bot_token>"
export FREQTRADE__TELEGRAM__CHAT_ID="<chat_id>"
```

For BNB-discounted fees the spec assumes, **enable “Pay fees with BNB” in
Binance Settings** (the bot doesn't toggle this — it's an account flag).

## Run

### Backtest (full pipeline)

```bash
chmod +x backtest.sh
./backtest.sh
```

This walks through, in order:

1. `freqtrade download-data` for `BTC/USDT` on `4h` + `1h` + `1d` across
   `2022-01-01 → 2026-01-01`. Idempotent — re-runs only fetch missing
   candles.
2. `freqtrade lookahead-analysis` — proves the strategy uses no future
   data. Required by spec before any backtest is trusted.
3. `freqtrade recursive-analysis` — confirms indicators converge as more
   bars are added (no instability).
4. `freqtrade backtesting` over the full timerange, trades exported to
   `user_data/backtest_results/`.

**Acceptance criteria (from spec):**

| Metric         | Threshold |
|----------------|-----------|
| Win Rate       | > 58%     |
| Profit Factor  | > 1.5     |
| Sharpe Ratio   | > 0.8     |
| Max Drawdown   | < 20%     |
| Trade count    | > 150     |

If any fails, tune (start with `IntParameter`/`DecimalParameter` fields
in the strategy) and re-run. **Do NOT promote to dry-run** until all
five pass.

### Dry-run (paper trade, 2 months minimum)

```bash
freqtrade trade --userdir ./user_data --config config.dryrun.json
```

Watch `user_data/logs/freqtrade_dryrun.log` and the Telegram channel.
**Dry-run acceptance:** Sharpe > 0.8 **and** drawdown < 15% over 2
months. Anything less → back to tuning, do not flip to live.

### Live (real funds)

> ⚠️ **Triple-check** that backtest + dry-run gates above are met before
> running this. Live trading is irreversible.

```bash
freqtrade trade --userdir ./user_data --config config.json
```

To stop: `Ctrl-C` once. Freqtrade flushes the open-trades state on a clean
shutdown so you can resume later without losing positions.

## Tests

```bash
pytest -q
```

Covers:
- `RegimeDetector` whipsaw guard + classification rules + warm-up safety.
- Strategy indicator pipeline emits the expected columns.
- `custom_stoploss` branches correctly per `enter_tag`.
- `custom_stake_amount` honours per-tag wallet shares + the 10 USDT floor.
- `custom_entry_price` / `custom_exit_price` keep LIMITs Maker-side.
- `protections` includes the 5%/15% drawdown stops + cooldown.

## Cost model (built into entry filters)

| Item                       | Value     |
|----------------------------|-----------|
| Maker commission (BNB)     | 0.075% × 2 = 0.15% round-trip |
| Slippage assumption        | 0.05% per round-trip          |
| **Total cycle cost**       | **0.20%** |
| Minimum expected move (`ATR%`) gate | **0.25%** (= cost + 0.05% margin) |

The `expected_move_pct > 0.25` filter in `populate_entry_trend` skips
trades that mathematically can't cover their own fees.

## Configuration knobs (per-strategy hyperparameters)

All hyperparameters are exposed as Freqtrade `IntParameter` /
`DecimalParameter` so you can `freqtrade hyperopt` them later:

| Param                       | Default | Strategy        |
|-----------------------------|---------|-----------------|
| `mr_rsi_oversold`           | 30      | mean_reversion  |
| `mr_stoch_oversold`         | 25      | mean_reversion  |
| `mr_rsi_overbought`         | 65      | mean_reversion  |
| `mr_bb_band_tolerance_pct`  | 0.5     | mean_reversion  |
| `mr_stoploss`               | -0.03   | mean_reversion  |
| `trend_rsi_min`             | 35      | trend_pullback  |
| `trend_rsi_max`             | 55      | trend_pullback  |

## What this bot does NOT do

By spec — and by deliberate choice — this bot has no:
- Margin, futures, leverage, or shorting.
- DCA / position averaging (single-entry per leg).
- Cross-pair correlation logic (BTC/USDT only).
- Auto-promote-to-live (you make that call after acceptance metrics).

## Troubleshooting

### Windows: `Cannot connect to host api.binance.com:443 [Could not contact DNS servers]`
`aiodns` (the C-based async DNS resolver) can't read Windows' DNS
configuration, so it fails with this message — even though normal `requests`
calls to the same host work. Fix:

```bash
pip uninstall -y aiodns
```

`aiohttp` then falls back to its `ThreadedResolver` which uses Python's
`socket.getaddrinfo` (the same path `requests` uses) and resolves cleanly.
Re-running `./backtest.sh` after this works.

### `attempted relative import with no known parent package`
Freqtrade loads strategy files by file path, not as a Python package, so
relative imports like `from .regime_detector import RegimeDetector` fail.
The shipped strategy uses a `try: bare import / except: package path`
pattern so it loads under BOTH Freqtrade (bare) and pytest (package). If
you add your own helper modules in `user_data/strategies/`, follow the
same idiom.

### Other gotchas
- **`freqtrade lookahead-analysis` reports `False positive on …`:** an
  indicator is reading a future bar. Most common cause: using
  `dataframe.shift(-N)` anywhere. The shipped strategy uses no negative
  shifts.
- **Order rejected as Taker:** the Maker offset in `MAKER_OFFSET_PCT`
  was too small for the current spread. Bump to 0.001 (0.1%) and retest.
- **Telegram silent:** verify `FREQTRADE__TELEGRAM__TOKEN` is exported in
  the SAME shell where `freqtrade trade` runs, and that `telegram.enabled`
  is `true` in the config you passed via `--config`.
- **Git Bash on Windows can't find `freqtrade`:** `PATH` set in PowerShell
  doesn't propagate to bash. Export inside bash:
  `export PATH="$PWD/.venv/Scripts:$PATH"` (note: forward slashes; bash on
  Git Bash converts.) Then `bash backtest.sh`.

## Initial backtest results (reference)

Backtest run 2026-05-30 on BTC/USDT, 4h, `2022-08-05 → 2026-01-01`,
dry-run wallet 10k USDT, with the shipped parameter defaults (no
hyperopt). **Do NOT promote to live — these do not meet the spec's
acceptance criteria.**

| Metric         | Achieved | Spec target | Pass? |
|----------------|---------:|------------:|:-----:|
| Total trades   | 8        | > 150       | ❌    |
| Win rate       | 0%       | > 58%       | ❌    |
| Profit factor  | 0.00     | > 1.5       | ❌    |
| Sharpe         | -0.14    | > 0.8       | ❌    |
| Max drawdown   | 0.70%    | < 20%       | ✅ (only because trades are tiny) |
| Total P&L      | -0.70%   | —           | —     |
| Market change  | +283%    | —           | —     |

The strategy implements the spec faithfully, but the combined filter
requirements (8 conditions for mean-reversion, 10 for trend-pullback,
all simultaneous) are too restrictive: 8 trades in 3.5 years. The
trend-pullback exit `close < EMA50 × 0.99` is also structurally
adjacent to the entry zone (between EMA21 and EMA50) — entries fill
~1% from their own stop. Use `freqtrade hyperopt` to tune the exposed
`IntParameter` / `DecimalParameter` fields before any further attempt
to promote, or revisit the exit rules.
