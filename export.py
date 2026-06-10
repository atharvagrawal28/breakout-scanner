"""
export.py — Build a polished multi-sheet Excel workbook from scan results.

Sheets:
  - Signals    : strict pass of ALL 5 conditions (the exact columns requested)
  - Watchlist  : near-misses (score 3-4), ranked, with the missing condition
  - All Stocks : every evaluated symbol with score + per-condition breakdown
  - Summary    : run metadata and condition definitions
"""

from __future__ import annotations

import io
from datetime import datetime

import pandas as pd

import scanner


def _autosize(ws, df, start_row=1):
    for i, col in enumerate(df.columns):
        width = max(len(str(col)), *(len(str(v)) for v in df[col].astype(str))) if len(df) else len(str(col))
        ws.set_column(i, i, min(max(width + 2, 10), 45))


def build_workbook(scan_df: pd.DataFrame, run_dt: datetime = None) -> bytes:
    run_dt = run_dt or datetime.now()
    sig = scanner.signals_only(scan_df)
    wl = scanner.watchlist(scan_df, min_score=3)

    all_cols = (scanner.EXPORT_COLUMNS + ["Trendline Level", "Score", "Missing", "Sector"])
    all_cols = [c for c in all_cols if scan_df.empty or c in scan_df.columns]
    alldf = scan_df[all_cols].copy() if not scan_df.empty else pd.DataFrame(columns=all_cols)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        wb = xw.book
        hdr = wb.add_format({"bold": True, "bg_color": "#1F4E78", "font_color": "white",
                             "border": 1, "align": "center", "valign": "vcenter"})
        green = wb.add_format({"bg_color": "#C6EFCE"})
        title = wb.add_format({"bold": True, "font_size": 14})
        small = wb.add_format({"font_size": 10, "italic": True, "font_color": "#555555"})

        def write_sheet(name, df, note=None):
            df.to_excel(xw, sheet_name=name, startrow=1, index=False)
            ws = xw.sheets[name]
            for c, col in enumerate(df.columns):
                ws.write(1, c, col, hdr)
            if note:
                ws.write(0, 0, note, small)
            _autosize(ws, df)
            ws.freeze_panes(2, 0)
            if len(df):
                ws.autofilter(1, 0, 1 + len(df), len(df.columns) - 1)
            return ws

        # Signals
        note = f"Strict signals — ALL 5 conditions met.  Run: {run_dt:%Y-%m-%d %H:%M}"
        ws = write_sheet("Signals", sig if not sig.empty else
                         pd.DataFrame(columns=scanner.EXPORT_COLUMNS), note)
        if sig.empty:
            ws.write(3, 0, "No stocks passed all 5 conditions today. See the Watchlist sheet.")

        # Watchlist
        write_sheet("Watchlist", wl if not wl.empty else
                    pd.DataFrame(columns=["Symbol", "Company Name", "Score", "Missing"]),
                    "Near-misses (3-4 of 5). 'Missing' shows which condition(s) failed.")

        # All
        write_sheet("All Stocks", alldf,
                    "Every evaluated stock, ranked by Score (5 = full signal).")

        # Summary
        s = wb.add_worksheet("Summary")
        s.write(0, 0, "Stock Breakout Scanner", title)
        _dd = ""
        if not scan_df.empty and "Data Date" in scan_df.columns:
            try:
                _dd = scan_df["Data Date"].mode().iloc[0]
            except Exception:
                _dd = str(scan_df["Data Date"].iloc[0])
        s.write(2, 0, f"Run time: {run_dt:%Y-%m-%d %H:%M:%S}  |  Data as of EOD: {_dd}")
        s.write(6, 0, "Note: 'Current Price' = last completed daily close (EOD), not a live "
                       "intraday price. Ties exactly to NSE Bhavcopy.", small)
        s.write(3, 0, f"Stocks evaluated: {len(scan_df)}")
        s.write(4, 0, f"Strict signals (all 5): {len(sig)}")
        s.write(5, 0, f"Watchlist (3-4 of 5): {len(wl)}")
        s.write(7, 0, "Conditions", title)
        defs = [
            "1. RSI(14) between 50 and 65 (inclusive)",
            "2. Close above DEMA20, DEMA50, DEMA100 and DEMA200",
            "3. Current volume > average volume of the last 10 trading days",
            "4. Descending-trendline breakout (close above falling resistance)",
            "5. Retest confirmed (pullback to the line held above it)",
        ]
        for i, d in enumerate(defs):
            s.write(8 + i, 0, d)
        s.write(15, 0, "Data sources: Yahoo Finance (yfinance) with NSE official Bhavcopy fallback.", small)
        s.write(17, 0, "DISCLAIMER", title)
        disc = [
            "This is an educational technical-analysis tool, NOT investment advice and",
            "NOT a stock recommendation. It is not provided by a SEBI-registered Research",
            "Analyst or Investment Adviser. The signals are rule-based screens only.",
            "Do your own research / consult a SEBI-registered adviser before trading.",
            "No assurance or guarantee of returns. Trading involves risk of loss.",
        ]
        for i, d in enumerate(disc):
            s.write(18 + i, 0, d)
        s.set_column(0, 0, 80)

    buf.seek(0)
    return buf.getvalue()
