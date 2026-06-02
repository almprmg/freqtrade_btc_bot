"""Train XGBoost to predict optimal BTC allocation (0-1) from 30+ features.

Target: forward 30-day return RANK (relative to history) — we want to be
heavy in BTC when next 30d is in top quartile of historical returns.

Features (per bar):
  - returns: 7d, 14d, 30d, 60d, 90d, 180d
  - volatility: 30d std, 90d std, vol-of-vol
  - moving avg ratios: close/EMA50, close/EMA200, EMA50/EMA200
  - momentum: ROC 10d, ROC 30d, ROC 90d
  - oscillators: RSI 14, RSI 30, CCI 20, MFI 14
  - bollinger: %B 20, width 20
  - trend: ADX 14, +DI, -DI
  - volume: vol z-score 30, OBV slope
  - regime indicators: 30d high distance, 60d high distance

Target: target_btc_pct = clamp(z_score(forward_30d_return), 0, 1)
   - bottom 30% of forward returns -> target 0.0
   - top 30% -> target 1.0
   - middle -> linear interpolation

This is supervised regression, NOT prediction. We're learning a mapping
from current state -> ideal historical allocation (in hindsight). The
inference at runtime gives a "size" recommendation.

Walk-forward train: 2020-2023, validate 2024, test 2025-2026.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "user_data" / "data" / "binance" / "BTC_USDT-1d.feather"
OUT_MODEL = REPO / "user_data" / "data" / "xgb_sizing.pkl"
OUT_PREDS = REPO / "user_data" / "data" / "xgb_sizing_preds.feather"


def features(df):
    import talib.abstract as ta
    f = pd.DataFrame(index=df.index)

    # Returns
    for w in [7, 14, 30, 60, 90, 180]:
        f[f"ret_{w}d"] = df["close"].pct_change(w)

    # Volatility
    log_ret = np.log(df["close"] / df["close"].shift(1))
    f["vol_30d"] = log_ret.rolling(30).std()
    f["vol_90d"] = log_ret.rolling(90).std()
    f["vol_of_vol"] = f["vol_30d"].rolling(60).std()

    # EMAs
    ema50 = ta.EMA(df, timeperiod=50)
    ema200 = ta.EMA(df, timeperiod=200)
    f["ratio_ema50"] = df["close"] / ema50
    f["ratio_ema200"] = df["close"] / ema200
    f["ema50_ema200"] = ema50 / ema200

    # Momentum
    f["roc_10"] = df["close"].pct_change(10)
    f["roc_30"] = df["close"].pct_change(30)
    f["roc_90"] = df["close"].pct_change(90)

    # Oscillators
    f["rsi_14"] = ta.RSI(df, timeperiod=14)
    f["rsi_30"] = ta.RSI(df, timeperiod=30)
    f["cci_20"] = ta.CCI(df, timeperiod=20)
    f["mfi_14"] = ta.MFI(df, timeperiod=14)

    # Bollinger
    bb = ta.BBANDS(df, timeperiod=20)
    f["bb_pct_b"] = (df["close"] - bb["lowerband"]) / (bb["upperband"] - bb["lowerband"]).replace(0, np.nan)
    f["bb_width"] = (bb["upperband"] - bb["lowerband"]) / bb["middleband"]

    # ADX
    adx = ta.ADX(df, timeperiod=14)
    plus_di = ta.PLUS_DI(df, timeperiod=14)
    minus_di = ta.MINUS_DI(df, timeperiod=14)
    f["adx"] = adx
    f["plus_di"] = plus_di
    f["minus_di"] = minus_di

    # Volume
    f["vol_z_30"] = (df["volume"] - df["volume"].rolling(30).mean()) / df["volume"].rolling(30).std().replace(0, np.nan)
    obv = ta.OBV(df)
    f["obv_slope"] = (obv - obv.shift(30)) / obv.shift(30).abs().replace(0, np.nan)

    # Distance from rolling highs (drawdown)
    high_30 = df["high"].rolling(30).max()
    high_90 = df["high"].rolling(90).max()
    f["dist_30d_high"] = (df["close"] - high_30) / high_30
    f["dist_90d_high"] = (df["close"] - high_90) / high_90
    return f


def build_target(df):
    """Target: rank of forward 30d return, normalized 0-1."""
    fwd_30d = df["close"].shift(-30) / df["close"] - 1
    # Rank within rolling 365-day window
    rank = fwd_30d.rolling(365, min_periods=60).rank(pct=True)
    return rank


def main():
    try:
        from xgboost import XGBRegressor
    except ImportError:
        print("Installing xgboost...")
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "xgboost"])
        from xgboost import XGBRegressor

    df = pd.read_feather(DATA)
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df.set_index("date").sort_index()

    feats = features(df)
    target = build_target(df)

    data = feats.join(target.rename("y")).dropna()
    print(f"data rows: {len(data)}, features: {len(feats.columns)}")
    print(f"date range: {data.index.min().date()} to {data.index.max().date()}")

    # Walk-forward split
    train = data.loc[:"2023-12-31"]
    val = data.loc["2024-01-01":"2024-12-31"]
    test = data.loc["2025-01-01":]

    X_train, y_train = train.drop(columns=["y"]).values, train["y"].values
    X_val, y_val = val.drop(columns=["y"]).values, val["y"].values
    X_test, y_test = test.drop(columns=["y"]).values, test["y"].values
    print(f"  train: {len(X_train)} rows ({train.index.min().date()}->{train.index.max().date()})")
    print(f"  val:   {len(X_val)} rows ({val.index.min().date() if len(val) else '-'}->{val.index.max().date() if len(val) else '-'})")
    print(f"  test:  {len(X_test)} rows ({test.index.min().date() if len(test) else '-'}->{test.index.max().date() if len(test) else '-'})")

    model = XGBRegressor(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, random_state=42,
        early_stopping_rounds=20,
    )
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

    # Metrics
    from sklearn.metrics import mean_absolute_error
    pred_train = model.predict(X_train)
    pred_val = model.predict(X_val)
    pred_test = model.predict(X_test)
    print()
    print(f"MAE train: {mean_absolute_error(y_train, pred_train):.4f}")
    print(f"MAE val:   {mean_absolute_error(y_val, pred_val):.4f}")
    print(f"MAE test:  {mean_absolute_error(y_test, pred_test):.4f}")
    print(f"Naive (mean): {abs(y_test - 0.5).mean():.4f}")

    # Feature importance
    imp = pd.Series(model.feature_importances_, index=feats.columns).sort_values(ascending=False)
    print("\nTop 10 features:")
    print(imp.head(10).to_string())

    # Predict for ALL dates (training included for completeness)
    full_X = data.drop(columns=["y"]).values
    full_pred = model.predict(full_X)
    out = pd.DataFrame({"date": data.index, "predicted_target": full_pred})
    out.to_feather(OUT_PREDS)
    print(f"\nSaved predictions: {OUT_PREDS}")

    # Save model
    import pickle
    with OUT_MODEL.open("wb") as f:
        pickle.dump({"model": model, "feature_cols": list(feats.columns)}, f)
    print(f"Saved model: {OUT_MODEL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
