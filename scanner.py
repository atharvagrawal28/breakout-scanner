"""
scanner.py — Core engine for the Indian-stock breakout scanner.

Five technical conditions over an NSE universe:
  1. RSI(14) between 50 and 65 (inclusive)
  2. Close above all major DEMAs: DEMA20, DEMA50, DEMA100, DEMA200
  3. Volume confirmation: current volume > average volume of last 10 trading days
  4. Descending-trendline breakout: close above a falling resistance line
  5. Retest confirmation: after breakout, price retested the line and held above it

A stock passing ALL FIVE is a "Signal". Stocks passing 3-4 land on a ranked
"Watchlist". Free libraries only: pandas, numpy, scipy, yfinance.
"""
from __future__ import annotations

import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

RSI_PERIOD = 14
RSI_LOW = 50.0
RSI_HIGH = 65.0
DEMA_PERIODS = (20, 50, 100, 200)
VOL_AVG_DAYS = 10
PIVOT_WINDOW = 3
TREND_LOOKBACK = 90
MIN_PIVOTS = 2
BREAKOUT_LOOKBACK = 15
RETEST_TOLERANCE = 0.015
BREAKOUT_BUFFER = 0.0
DATA_PERIOD = "2y"
MIN_BARS = 250


# ----------------------------- Indicators ----------------------------- #
def _wilder_rma(x: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothed average (RMA), SMA-seeded — matches TradingView RSI."""
    arr = x.to_numpy(dtype=float)
    out = np.full(len(arr), np.nan)
    if len(arr) <= period:
        return pd.Series(out, index=x.index)
    # delta[0] is NaN, so seed from values 1..period
    prev = np.nanmean(arr[1:period + 1])
    out[period] = prev
    for i in range(period + 1, len(arr)):
        prev = (prev * (period - 1) + arr[i]) / period
        out[i] = prev
    return pd.Series(out, index=x.index)


def rsi(close: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = _wilder_rma(gain, period)
    avg_loss = _wilder_rma(loss, period)
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100 - (100 / (1 + rs))
    out = out.where(avg_loss != 0, 100.0)
    return out


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def dema(close: pd.Series, period: int) -> pd.Series:
    e1 = ema(close, period)
    e2 = ema(e1, period)
    return 2 * e1 - e2


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range (Wilder). Measures volatility for stop/target sizing."""
    h, l, c = df["High"], df["Low"], df["Close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


# ------------------- Swing highs + descending trendline ------------------- #
def find_swing_highs(high: np.ndarray, window: int = PIVOT_WINDOW) -> list:
    idx = []
    n = len(high)
    for i in range(window, n - window):
        seg = high[i - window:i + window + 1]
        if high[i] == seg.max() and np.argmax(seg) == window:
            idx.append(i)
    return idx


@dataclass
class TrendlineResult:
    has_breakout: bool = False
    retest_confirmed: bool = False
    line_now: float = np.nan
    slope: float = np.nan
    breakout_idx: Optional[int] = None
    p1_idx: Optional[int] = None
    p2_idx: Optional[int] = None


def detect_trendline(df: pd.DataFrame,
                     lookback: int = TREND_LOOKBACK,
                     pivot_window: int = PIVOT_WINDOW,
                     breakout_lookback: int = BREAKOUT_LOOKBACK,
                     retest_tol: float = RETEST_TOLERANCE,
                     buffer: float = BREAKOUT_BUFFER) -> TrendlineResult:
    res = TrendlineResult()
    if len(df) < 30:
        return res
    if len(df) < lookback + pivot_window + 5:
        lookback = max(30, len(df) - pivot_window - 5)

    seg = df.iloc[-lookback:]
    high = seg["High"].to_numpy(dtype=float)
    low = seg["Low"].to_numpy(dtype=float)
    close = seg["Close"].to_numpy(dtype=float)
    n = len(seg)

    pivots = find_swing_highs(high, pivot_window)
    if len(pivots) < MIN_PIVOTS:
        return res

    best = None
    for a in range(len(pivots)):
        for b in range(a + 1, len(pivots)):
            i1, i2 = pivots[a], pivots[b]
            if i2 - i1 < pivot_window:
                continue
            y1, y2 = high[i1], high[i2]
            slope = (y2 - y1) / (i2 - i1)
            if slope >= 0:
                continue
            line = y1 + slope * (np.arange(n) - i1)
            inner = [p for p in pivots if i1 < p < i2]
            if any(high[p] > line[p] * (1 + 0.003) for p in inner):
                continue
            score = (i2 - i1) + i2
            if best is None or score > best[0]:
                best = (score, i1, i2, slope, line)

    if best is None:
        return res

    _, i1, i2, slope, line = best
    res.slope = float(slope)
    res.p1_idx = len(df) - lookback + i1
    res.p2_idx = len(df) - lookback + i2
    res.line_now = float(line[-1])

    start = max(i2 + 1, n - breakout_lookback)
    breakout_local = None
    for j in range(max(start, 1), n):
        if close[j] > line[j] * (1 + buffer) and close[j - 1] <= line[j - 1] * (1 + buffer):
            breakout_local = j
            break

    if breakout_local is None:
        return res

    res.has_breakout = True
    res.breakout_idx = len(df) - lookback + breakout_local

    held_above_now = close[-1] > line[-1]
    retest = False
    for j in range(breakout_local + 1, n):
        if low[j] <= line[j] * (1 + retest_tol) and close[j] >= line[j]:
            retest = True
            break
    res.retest_confirmed = bool(retest and held_above_now)
    return res


# ----------------------------- Evaluation ----------------------------- #
CONDITION_LABELS = {
    "c1_rsi": "RSI 50-65",
    "c2_dema": "Above all DEMAs",
    "c3_vol": "Volume > 10d avg",
    "c4_breakout": "Trendline breakout",
    "c5_retest": "Retest held",
}


def evaluate(df: pd.DataFrame, company: str, sector: str, symbol: str,
             params: Optional[dict] = None) -> Optional[dict]:
    p = params or {}
    if df is None or len(df) < MIN_BARS:
        return None
    df = df.dropna(subset=["Close", "High", "Low", "Volume"]).copy()
    if len(df) < MIN_BARS:
        return None

    close = df["Close"]
    r = rsi(close, p.get("rsi_period", RSI_PERIOD))
    d20, d50, d100, d200 = dema(close, 20), dema(close, 50), dema(close, 100), dema(close, 200)

    cur_close = float(close.iloc[-1])
    cur_rsi = float(r.iloc[-1])
    cur_vol = float(df["Volume"].iloc[-1])
    avg_vol10 = float(df["Volume"].iloc[-(VOL_AVG_DAYS + 1):-1].mean())
    vol_ratio = cur_vol / avg_vol10 if avg_vol10 else np.nan
    v20, v50, v100, v200 = (float(d20.iloc[-1]), float(d50.iloc[-1]),
                            float(d100.iloc[-1]), float(d200.iloc[-1]))

    rsi_lo = p.get("rsi_low", RSI_LOW)
    rsi_hi = p.get("rsi_high", RSI_HIGH)
    c1 = bool(rsi_lo <= cur_rsi <= rsi_hi)
    c2 = bool(cur_close > v20 and cur_close > v50 and cur_close > v100 and cur_close > v200)
    c3 = bool(cur_vol > avg_vol10) if not np.isnan(avg_vol10) else False

    tl = detect_trendline(df,
                          lookback=p.get("trend_lookback", TREND_LOOKBACK),
                          pivot_window=p.get("pivot_window", PIVOT_WINDOW),
                          breakout_lookback=p.get("breakout_lookback", BREAKOUT_LOOKBACK),
                          retest_tol=p.get("retest_tol", RETEST_TOLERANCE))
    c4, c5 = tl.has_breakout, tl.retest_confirmed

    # --- ATR-based risk plan (1 : 2 risk/reward) ---
    atr_val = float(atr(df, 14).iloc[-1])
    stop_mult = p.get("atr_stop_mult", 1.5)
    rr_ratio = p.get("rr_ratio", 2.0)
    stop_loss = cur_close - stop_mult * atr_val
    target = cur_close + stop_mult * rr_ratio * atr_val
    risk_pct = (cur_close - stop_loss) / cur_close * 100 if cur_close else np.nan
    reward_pct = (target - cur_close) / cur_close * 100 if cur_close else np.nan

    conds = {"c1_rsi": c1, "c2_dema": c2, "c3_vol": c3, "c4_breakout": c4, "c5_retest": c5}
    score = int(sum(conds.values()))
    missing = [CONDITION_LABELS[k] for k, ok in conds.items() if not ok]

    return {
        "Symbol": symbol, "Company Name": company, "Sector": sector,
        "Data Date": str(df.index[-1].date()) if hasattr(df.index[-1], "date") else "",
        "Current Price": round(cur_close, 2), "RSI": round(cur_rsi, 2),
        "DEMA20": round(v20, 2), "DEMA50": round(v50, 2),
        "DEMA100": round(v100, 2), "DEMA200": round(v200, 2),
        "Current Volume": int(cur_vol),
        "10 Day Average Volume": int(avg_vol10) if not np.isnan(avg_vol10) else None,
        "Volume Ratio": round(vol_ratio, 2) if not np.isnan(vol_ratio) else None,
        "Trendline Breakout": "Yes" if c4 else "No",
        "Retest Confirmed": "Yes" if c5 else "No",
        "Trendline Level": round(tl.line_now, 2) if not np.isnan(tl.line_now) else None,
        "ATR": round(atr_val, 2) if not np.isnan(atr_val) else None,
        "Stop Loss": round(stop_loss, 2) if not np.isnan(atr_val) else None,
        "Target": round(target, 2) if not np.isnan(atr_val) else None,
        "Risk %": round(risk_pct, 2) if not np.isnan(risk_pct) else None,
        "Reward %": round(reward_pct, 2) if not np.isnan(reward_pct) else None,
        "Risk:Reward": f"1:{rr_ratio:g}",
        "Score": score, "Missing": ", ".join(missing) if missing else "",
        "_cond": conds, "_trendline": tl, "_passes_all": score == 5,
    }


# ------------------------- Data download ------------------------- #
def download_history(tickers: list, period: str = DATA_PERIOD,
                     batch_size: int = 40, pause: float = 1.0,
                     progress_cb=None) -> dict:
    import yfinance as yf
    out = {}
    batches = [tickers[i:i + batch_size] for i in range(0, len(tickers), batch_size)]
    done = 0
    for batch in batches:
        data = None
        for attempt in range(3):
            try:
                data = yf.download(batch, period=period, interval="1d",
                                   auto_adjust=False, progress=False,
                                   group_by="ticker", threads=True)
                if data is not None and len(data) > 0:
                    break
            except Exception:
                pass
            time.sleep(2 * (attempt + 1))
        if data is not None and len(data) > 0:
            for t in batch:
                try:
                    if isinstance(data.columns, pd.MultiIndex):
                        lvl0 = set(data.columns.get_level_values(0))
                        if t in lvl0:
                            sub = data[t].copy()
                        else:
                            # single-ticker frames come back as (field, ticker)
                            sub = data.xs(t, axis=1, level=-1).copy()
                    else:
                        sub = data.copy()
                    sub = sub.dropna(how="all")
                    if len(sub):
                        out[t] = sub
                except Exception:
                    pass
        done += len(batch)
        if progress_cb:
            progress_cb(done, len(tickers))
        time.sleep(pause)
    return out


# ------------------------- Universe + full scan ------------------------- #
def load_universe(path=None) -> pd.DataFrame:
    if path is None:
        path = Path(__file__).parent / "data" / "universe.csv"
    return pd.read_csv(path, dtype=str).fillna("")


def run_scan(universe: pd.DataFrame = None, params: dict = None,
             progress_cb=None, status_cb=None, drop_incomplete: bool = True,
             use_nse_fallback: bool = True) -> pd.DataFrame:
    if universe is None:
        universe = load_universe()
    universe = universe[universe["tradable"] == "Y"].copy()
    tickers = universe["ticker"].tolist()
    if status_cb:
        status_cb(f"Downloading price history for {len(tickers)} stocks...")
    hist = download_history(tickers, progress_cb=progress_cb)

    # --- NSE Bhavcopy fallback / authoritative history store -----------------
    if use_nse_fallback:
        try:
            import nse_data
            if hist:
                nse_data.save_histories_to_store(hist)   # back up whatever Yahoo gave us
            nse_data.update_store_with_bhavcopy()         # append latest official EOD bar
            missing = [t for t in tickers if t not in hist]
            if missing:
                if status_cb:
                    status_cb(f"Yahoo missed {len(missing)} stocks - using NSE store...")
                for t in missing:
                    sub = nse_data.load_from_store(t, min_bars=MIN_BARS)
                    if sub is not None:
                        hist[t] = sub
        except Exception as _e:
            if status_cb:
                status_cb(f"NSE fallback unavailable: {_e}")

    import datetime as _dt
    today = _dt.date.today()
    rows = []
    meta = {r["ticker"]: r for _, r in universe.iterrows()}
    for t, df in hist.items():
        m = meta.get(t, {})
        if drop_incomplete and len(df) and hasattr(df.index[-1], "date") and df.index[-1].date() == today:
            df = df.iloc[:-1]
        try:
            rec = evaluate(df, company=m.get("company_name", t),
                           sector=m.get("sector", ""),
                           symbol=m.get("symbol", t.replace(".NS", "")),
                           params=params)
        except Exception:
            rec = None
        if rec:
            rows.append(rec)
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    return out.sort_values(["Score", "Volume Ratio"], ascending=[False, False]).reset_index(drop=True)


EXPORT_COLUMNS = [
    "Symbol", "Company Name", "Current Price", "RSI",
    "DEMA20", "DEMA50", "DEMA100", "DEMA200",
    "Current Volume", "10 Day Average Volume", "Volume Ratio",
    "Trendline Breakout", "Retest Confirmed",
]


def signals_only(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    sig = df[df["_passes_all"]].copy()
    return sig[EXPORT_COLUMNS].reset_index(drop=True)


def watchlist(df: pd.DataFrame, min_score: int = 3) -> pd.DataFrame:
    if df.empty:
        return df
    wl = df[(df["Score"] >= min_score) & (~df["_passes_all"])].copy()
    cols = EXPORT_COLUMNS[:-2] + ["Trendline Breakout", "Retest Confirmed",
                                  "Score", "Missing", "Sector"]
    return wl[cols].reset_index(drop=True)
