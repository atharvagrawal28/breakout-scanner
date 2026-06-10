"""
backtest.py — Historical win-rate test for the 5-condition breakout setup.

What it does
------------
Replays history bar-by-bar. Whenever a stock met ALL 5 conditions on a given day
(using only data available UP TO that day — no look-ahead), it simulates a trade:

  entry  = next day's close
  stop   = entry - stop_mult * ATR        (default 1.5 x ATR)
  target = entry + stop_mult * rr * ATR   (default 1:2 risk/reward)

It then walks forward up to `forward_days` and records whether the target or the
stop was hit first (or marks-to-market at the horizon). Finally it reports the
win-rate, average return, average win/loss and expectancy.

This is a SIMPLIFIED simulation for education: it ignores slippage, brokerage,
taxes, gap risk and liquidity, and assumes you could transact at the close. Real
results will differ. Past performance does not guarantee future results.

Usage
-----
    python backtest.py                 # default: 60 stocks, 20-day horizon
    python backtest.py 120 30          # 120 stocks, 30-day horizon
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

import scanner

RESULTS = Path(__file__).parent / "results"
RESULTS.mkdir(exist_ok=True)


def backtest_symbol(df: pd.DataFrame, symbol: str, params: dict,
                    forward_days: int = 20) -> list[dict]:
    df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"]).copy()
    if len(df) < scanner.MIN_BARS + forward_days + 5:
        return []

    close = df["Close"]
    rsi = scanner.rsi(close, params.get("rsi_period", 14))
    d20 = scanner.dema(close, 20); d50 = scanner.dema(close, 50)
    d100 = scanner.dema(close, 100); d200 = scanner.dema(close, 200)
    atr = scanner.atr(df, 14)
    vol = df["Volume"]
    avg10 = vol.shift(1).rolling(10).mean()

    rsi_lo = params.get("rsi_low", 50.0); rsi_hi = params.get("rsi_high", 65.0)
    lookback = params.get("trend_lookback", scanner.TREND_LOOKBACK)
    stop_mult = params.get("atr_stop_mult", 1.5); rr = params.get("rr_ratio", 2.0)

    # cheap vectorized conditions 1-3
    c1 = (rsi >= rsi_lo) & (rsi <= rsi_hi)
    c2 = (close > d20) & (close > d50) & (close > d100) & (close > d200)
    c3 = vol > avg10
    base = (c1 & c2 & c3).to_numpy()

    highs = df["High"].to_numpy(); lows = df["Low"].to_numpy()
    closes = close.to_numpy(); atrs = atr.to_numpy(); dates = df.index

    trades = []
    i = scanner.MIN_BARS
    end = len(df) - forward_days - 1
    while i < end:
        if base[i]:
            # expensive trendline + retest only when 1-3 already align
            sub = df.iloc[max(0, i - lookback - 5): i + 1]
            tl = scanner.detect_trendline(
                sub, lookback=lookback,
                pivot_window=params.get("pivot_window", scanner.PIVOT_WINDOW),
                breakout_lookback=params.get("breakout_lookback", scanner.BREAKOUT_LOOKBACK),
                retest_tol=params.get("retest_tol", scanner.RETEST_TOLERANCE))
            if tl.has_breakout and tl.retest_confirmed and not np.isnan(atrs[i]):
                entry = closes[i + 1]               # enter next day's close
                stop = entry - stop_mult * atrs[i]
                target = entry + stop_mult * rr * atrs[i]
                outcome, exitp, held = "open", entry, forward_days
                for k in range(i + 2, min(i + 2 + forward_days, len(df))):
                    if lows[k] <= stop:
                        outcome, exitp, held = "loss", stop, k - (i + 1); break
                    if highs[k] >= target:
                        outcome, exitp, held = "win", target, k - (i + 1); break
                else:
                    outcome, exitp = "timeout", closes[min(i + 1 + forward_days, len(df) - 1)]
                ret = (exitp - entry) / entry * 100
                trades.append({
                    "Symbol": symbol, "Signal Date": dates[i].date(),
                    "Entry": round(entry, 2), "Stop": round(stop, 2),
                    "Target": round(target, 2), "Exit": round(exitp, 2),
                    "Outcome": outcome, "Days Held": held, "Return %": round(ret, 2),
                })
                i += forward_days   # avoid overlapping trades on same name
        i += 1
    return trades


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    fwd = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    params = {}

    uni = scanner.load_universe()
    tickers = uni[uni["tradable"] == "Y"]["ticker"].tolist()[:n]
    meta = {r["ticker"]: r for _, r in uni.iterrows()}
    print(f"Backtesting {len(tickers)} stocks, {fwd}-day horizon...")

    hist = scanner.download_history(tickers)
    all_trades = []
    for t, df in hist.items():
        sym = meta.get(t, {}).get("symbol", t.replace(".NS", ""))
        all_trades += backtest_symbol(df, sym, params, forward_days=fwd)

    if not all_trades:
        print("No historical signals found in this sample.")
        return 0

    tr = pd.DataFrame(all_trades)
    wins = tr[tr["Outcome"] == "win"]; losses = tr[tr["Outcome"] == "loss"]
    closed = tr[tr["Outcome"].isin(["win", "loss"])]
    n_tr = len(tr)
    win_rate = len(wins) / len(closed) * 100 if len(closed) else float("nan")
    summary = {
        "Stocks tested": len(tickers),
        "Total signals/trades": n_tr,
        "Wins": len(wins), "Losses": len(losses),
        "Timeouts (held to horizon)": int((tr["Outcome"] == "timeout").sum()),
        "Win rate % (of closed)": round(win_rate, 1),
        "Avg return % (all)": round(tr["Return %"].mean(), 2),
        "Avg win %": round(wins["Return %"].mean(), 2) if len(wins) else 0,
        "Avg loss %": round(losses["Return %"].mean(), 2) if len(losses) else 0,
        "Expectancy % / trade": round(tr["Return %"].mean(), 2),
        "Avg days held": round(tr["Days Held"].mean(), 1),
    }

    print("\n=== BACKTEST SUMMARY ===")
    for k, v in summary.items():
        print(f"  {k:30s}: {v}")

    out = RESULTS / f"backtest_{datetime.now():%Y-%m-%d}.xlsx"
    with pd.ExcelWriter(out, engine="xlsxwriter") as xw:
        pd.DataFrame([summary]).T.rename(columns={0: "Value"}).to_excel(xw, sheet_name="Summary")
        tr.sort_values("Signal Date").to_excel(xw, sheet_name="Trades", index=False)
        disc = pd.DataFrame({"Disclaimer": [
            "Simplified educational backtest. Ignores slippage, brokerage, taxes,",
            "gap risk and liquidity. Assumes execution at close. Past performance",
            "does NOT guarantee future results. Not investment advice."]})
        disc.to_excel(xw, sheet_name="Disclaimer", index=False)
    print(f"\nSaved -> {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
