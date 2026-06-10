"""
manage_universe.py — Add or remove stocks from the scanner's universe.

The scan universe is just data/universe.csv. This tool lets you change it by plain
NSE symbol (e.g. RELIANCE) without hand-editing ISINs — it looks up the company name
and ISIN from NSE's official equity list automatically and validates the symbol.

Usage
-----
    python manage_universe.py list
    python manage_universe.py add RELIANCE TATAMOTORS
    python manage_universe.py remove YESBANK

After changing the universe:
  * Local: restart the app (Ctrl+C, then `streamlit run app.py`) and re-run the scan.
  * Deployed: commit & push universe.csv to GitHub (or edit it on github.com). The
    next daily scan picks up the change automatically — no code changes needed.

A newly added stock has no history in the local NSE store yet, but yfinance fetches
its full history on the very next scan, so it works immediately.
"""
from __future__ import annotations

import io
import sys
import urllib.request
from pathlib import Path

import pandas as pd

DATA = Path(__file__).parent / "data"
UNI = DATA / "universe.csv"
NSE_EQUITY_LIST = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
COLUMNS = ["company_name", "raw_name", "isin", "sector", "symbol", "ticker", "tradable"]


def _load_nse_list() -> pd.DataFrame:
    req = urllib.request.Request(NSE_EQUITY_LIST, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=25).read()
    df = pd.read_csv(io.BytesIO(raw))
    df.columns = [c.strip() for c in df.columns]
    return df


def _load_universe() -> pd.DataFrame:
    return pd.read_csv(UNI, dtype=str).fillna("")


def _save(df: pd.DataFrame):
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = ""
    df[COLUMNS].to_csv(UNI, index=False)


def cmd_list():
    df = _load_universe()
    tradable = (df["tradable"] == "Y").sum()
    print(f"Universe: {len(df)} stocks ({tradable} tradable on NSE).")
    print(df[["symbol", "company_name", "tradable"]].to_string(index=False))


def cmd_add(symbols):
    df = _load_universe()
    nse = _load_nse_list()
    have = set(df["symbol"].str.upper())
    added = []
    for sym in symbols:
        sym = sym.upper().strip()
        if sym in have:
            print(f"  - {sym}: already in universe, skipping.")
            continue
        row = nse[nse["SYMBOL"].str.upper() == sym]
        if row.empty:
            print(f"  ! {sym}: NOT found in NSE equity list — check the symbol.")
            continue
        r = row.iloc[0]
        df.loc[len(df)] = {
            "company_name": str(r["NAME OF COMPANY"]).strip(),
            "raw_name": str(r["NAME OF COMPANY"]).strip(),
            "isin": str(r["ISIN NUMBER"]).strip(),
            "sector": "", "symbol": sym, "ticker": f"{sym}.NS", "tradable": "Y",
        }
        added.append(sym)
        print(f"  + {sym}: added ({str(r['NAME OF COMPANY']).strip()}).")
    if added:
        _save(df)
        print(f"Saved. Universe now has {len(df)} stocks.")
    else:
        print("Nothing added.")


def cmd_remove(symbols):
    df = _load_universe()
    syms = {s.upper().strip() for s in symbols}
    before = len(df)
    keep = df[~df["symbol"].str.upper().isin(syms)]
    removed = before - len(keep)
    if removed:
        _save(keep)
        print(f"Removed {removed} stock(s). Universe now has {len(keep)} stocks.")
    else:
        print("No matching symbols found to remove.")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1].lower()
    args = sys.argv[2:]
    if cmd == "list":
        cmd_list()
    elif cmd == "add" and args:
        cmd_add(args)
    elif cmd == "remove" and args:
        cmd_remove(args)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
