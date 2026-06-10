"""
run_scan.py — Standalone, non-interactive scan runner.

Designed to be scheduled (GitHub Actions, Windows Task Scheduler, cron). It runs
the full scan over the 294-stock universe and writes:

  results/breakout_scan_<YYYY-MM-DD>.xlsx   (dated archive)
  results/latest.xlsx                       (what the dashboard reads)
  results/latest.parquet                    (fast machine-readable cache)
  results/last_run.txt                      (timestamp marker)

Usage:
    python run_scan.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

import scanner
import export

RESULTS = Path(__file__).parent / "results"
RESULTS.mkdir(exist_ok=True)


def main() -> int:
    start = datetime.now()
    print(f"[{start:%H:%M:%S}] Loading universe...")
    uni = scanner.load_universe()
    tradable = (uni["tradable"] == "Y").sum()
    print(f"  {len(uni)} stocks, {tradable} tradable on NSE.")

    def prog(done, total):
        print(f"  downloaded {done}/{total}", end="\r")

    print("Running scan (this pulls 2y of daily data per stock)...")
    df = scanner.run_scan(uni, progress_cb=prog)
    print()

    if df.empty:
        print("ERROR: no data returned (Yahoo may be rate-limiting). Aborting.")
        return 1

    sig = scanner.signals_only(df)
    wl = scanner.watchlist(df)
    print(f"Evaluated {len(df)} stocks | strict signals: {len(sig)} | watchlist: {len(wl)}")

    # Excel
    xlsx = export.build_workbook(df, run_dt=start)
    dated = RESULTS / f"breakout_scan_{start:%Y-%m-%d}.xlsx"
    dated.write_bytes(xlsx)
    (RESULTS / "latest.xlsx").write_bytes(xlsx)

    # Machine-readable cache for the dashboard (drop internal object columns)
    cache = df.drop(columns=[c for c in ("_cond", "_trendline") if c in df.columns])
    cache.to_parquet(RESULTS / "latest.parquet", index=False)
    (RESULTS / "last_run.txt").write_text(start.strftime("%Y-%m-%d %H:%M:%S"))

    if not sig.empty:
        print("\nToday's strict signals:")
        print(sig[["Symbol", "Current Price", "RSI", "Volume Ratio"]].to_string(index=False))

    print(f"\nSaved -> {dated.name}, latest.xlsx, latest.parquet")
    print(f"Done in {(datetime.now() - start).seconds}s.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
