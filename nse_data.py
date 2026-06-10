"""
nse_data.py — Official NSE Bhavcopy data source + local price-history store.

Why this exists
---------------
yfinance (Yahoo Finance) is an unofficial source that can rate-limit or break.
NSE's daily "Bhavcopy" is the *authoritative*, free, public end-of-day file for
every listed stock. This module:

  1. Downloads the latest official Bhavcopy (UDiFF format) from NSE's public
     archive — the same file traders download manually.
  2. Maintains a local price-history store (data/price_history.parquet) that grows
     a little every day, so indicators (DEMA200 etc.) always have history even if
     Yahoo is unavailable.
  3. Acts as a FALLBACK: the scanner uses yfinance first; whatever yfinance returns
     is saved into the store, and the daily Bhavcopy appends the latest authoritative
     bar. If yfinance fails for a stock, the scanner reads that stock from the store.

Compliance note: the Bhavcopy is a publicly published file intended for download.
This tool uses it for personal/educational analysis only and does NOT redistribute
the raw data commercially. Respect NSE's website terms (reasonable, infrequent
access — once per day).
"""
from __future__ import annotations

import datetime as _dt
import io
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
STORE = DATA_DIR / "price_history.parquet"   # long format: symbol, Date, OHLCV

_UA = {"User-Agent": "Mozilla/5.0", "Accept": "*/*"}
_BHAV_URL = ("https://nsearchives.nseindia.com/content/cm/"
             "BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip")


# --------------------------------------------------------------------------- #
# Bhavcopy download                                                            #
# --------------------------------------------------------------------------- #
def download_bhavcopy(date: _dt.date) -> Optional[pd.DataFrame]:
    """Download + parse one day's NSE Bhavcopy. Returns equity rows only, or None
    if that date has no file (weekend/holiday/not-yet-published)."""
    url = _BHAV_URL.format(ymd=date.strftime("%Y%m%d"))
    try:
        req = urllib.request.Request(url, headers=_UA)
        raw = urllib.request.urlopen(req, timeout=25).read()
        z = zipfile.ZipFile(io.BytesIO(raw))
        text = z.read(z.namelist()[0]).decode("utf-8", "ignore")
    except Exception:
        return None

    df = pd.read_csv(io.StringIO(text))
    # keep cash-market equity series only (EQ / BE / BZ etc. — EQ is the main one)
    df = df[df["SctySrs"].isin(["EQ", "BE"])].copy()
    out = pd.DataFrame({
        "symbol": df["TckrSymb"].astype(str).str.strip(),
        "isin": df["ISIN"].astype(str).str.strip(),
        "Date": pd.to_datetime(df["TradDt"]),
        "Open": pd.to_numeric(df["OpnPric"], errors="coerce"),
        "High": pd.to_numeric(df["HghPric"], errors="coerce"),
        "Low": pd.to_numeric(df["LwPric"], errors="coerce"),
        "Close": pd.to_numeric(df["ClsPric"], errors="coerce"),
        "Volume": pd.to_numeric(df["TtlTradgVol"], errors="coerce"),
    })
    return out.dropna(subset=["Close"])


def latest_bhavcopy(max_back: int = 7) -> tuple[Optional[_dt.date], Optional[pd.DataFrame]]:
    """Walk back from today to find the most recent published Bhavcopy."""
    today = _dt.date.today()
    for back in range(max_back + 1):
        d = today - _dt.timedelta(days=back)
        if d.weekday() >= 5:      # skip Sat/Sun quickly
            continue
        df = download_bhavcopy(d)
        if df is not None and len(df):
            return d, df
    return None, None


# --------------------------------------------------------------------------- #
# Local price-history store                                                     #
# --------------------------------------------------------------------------- #
def _load_store() -> pd.DataFrame:
    if STORE.exists():
        try:
            return pd.read_parquet(STORE)
        except Exception:
            pass
    return pd.DataFrame(columns=["symbol", "Date", "Open", "High", "Low", "Close", "Volume"])


def save_histories_to_store(hist: dict) -> int:
    """Persist {ticker: OHLCV-df} (e.g. from yfinance) into the long-format store.
    Tickers like 'RELIANCE.NS' are stored under symbol 'RELIANCE'."""
    rows = []
    for ticker, df in hist.items():
        if df is None or not len(df):
            continue
        sym = ticker.replace(".NS", "")
        d = df.reset_index()
        date_col = "Date" if "Date" in d.columns else d.columns[0]
        for _, r in d.iterrows():
            try:
                rows.append((sym, pd.to_datetime(r[date_col]),
                             float(r["Open"]), float(r["High"]), float(r["Low"]),
                             float(r["Close"]), float(r["Volume"])))
            except Exception:
                continue
    if not rows:
        return 0
    new = pd.DataFrame(rows, columns=["symbol", "Date", "Open", "High", "Low", "Close", "Volume"])
    return _merge_into_store(new)


def update_store_with_bhavcopy() -> int:
    """Append the latest authoritative Bhavcopy bar into the store."""
    d, bh = latest_bhavcopy()
    if bh is None:
        return 0
    bh = bh[["symbol", "Date", "Open", "High", "Low", "Close", "Volume"]]
    return _merge_into_store(bh)


def _merge_into_store(new: pd.DataFrame) -> int:
    DATA_DIR.mkdir(exist_ok=True)
    cur = _load_store()
    combined = new if cur.empty else pd.concat([cur, new], ignore_index=True)
    combined["Date"] = pd.to_datetime(combined["Date"])
    combined = (combined.drop_duplicates(subset=["symbol", "Date"], keep="last")
                        .sort_values(["symbol", "Date"]))
    combined.to_parquet(STORE, index=False)
    return len(new)


def load_from_store(ticker: str, min_bars: int = 1) -> Optional[pd.DataFrame]:
    """Return a wide OHLCV DataFrame (Date-indexed) for one ticker from the store."""
    sym = ticker.replace(".NS", "")
    store = _load_store()
    if store.empty:
        return None
    sub = store[store["symbol"] == sym].copy()
    if len(sub) < min_bars:
        return None
    sub = sub.sort_values("Date").set_index("Date")[["Open", "High", "Low", "Close", "Volume"]]
    return sub
