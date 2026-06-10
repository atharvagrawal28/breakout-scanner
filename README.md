# 📈 Stock Breakout Scanner

A daily technical scanner over a **294-stock NSE universe**. It returns the stocks
that satisfy a strict 5-condition breakout setup, a ranked **watchlist** of setups
still forming, and an ATR-based **trade plan** (stop/target) for each signal. Built
with free tools only.

> **Educational tool — not investment advice.** See [`DISCLAIMER.md`](DISCLAIMER.md).

## The 5 conditions (a "Signal" = all five)

| # | Condition |
|---|-----------|
| 1 | **RSI(14)** between **50 and 65** (inclusive) |
| 2 | **Close above all DEMAs**: DEMA20, DEMA50, DEMA100, DEMA200 |
| 3 | **Volume confirmation**: current volume > 10-day average volume |
| 4 | **Descending-trendline breakout**: close above falling resistance |
| 5 | **Retest confirmed**: price pulled back to the line and held above it |

Output columns: Symbol, Company Name, Current Price, RSI, DEMA20/50/100/200,
Current Volume, 10-Day Average Volume, Volume Ratio, Trendline Breakout (Yes/No),
Retest Confirmed (Yes/No), plus ATR / Stop Loss / Target / Risk% / Reward%.

## What's in the box

```
breakout-scanner/
├── app.py                 # Streamlit dashboard (scan, charts, education, Excel)
├── scanner.py             # Core engine: indicators, ATR, trendline, retest, scan
├── nse_data.py            # NSE Bhavcopy fallback + local price-history store
├── export.py              # Multi-sheet Excel builder
├── run_scan.py            # Standalone scheduled runner -> results/*.xlsx
├── backtest.py            # Historical win-rate test of the 5-condition setup
├── data/universe.csv      # 294 stocks mapped to NSE tickers (ISIN-matched)
├── data/price_history.parquet  # Authoritative price store (grows daily)
├── results/               # Dated Excel + latest.* (written by run_scan / Actions)
├── requirements.txt
├── .streamlit/config.toml
├── .github/workflows/daily-scan.yml   # Free daily auto-scan
├── .github/workflows/keep-alive.yml   # Keeps the Streamlit app awake
├── DISCLAIMER.md
└── README.md
```

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py          # dashboard
python run_scan.py            # headless one-shot -> Excel in results/
python backtest.py 60 20      # backtest 60 stocks, 20-day horizon
```

## Deploy free: GitHub + Streamlit Community Cloud

1. **Push** this folder to a (public) GitHub repo.
2. **Streamlit Cloud** → https://share.streamlit.io → *New app* → pick the repo and
   `app.py`. It installs `requirements.txt` and gives you a public URL.
3. **Password-protect** (App settings → Secrets):
   ```toml
   app_password = "your-password"
   ```
4. **Daily auto-scan**: enable the repo's **Actions** tab, set *Settings → Actions →
   Workflow permissions* to **Read and write**. `daily-scan.yml` runs pre-market each
   weekday, scans, and commits a fresh `results/latest.xlsx` + the price store.
5. **Keep app awake** (optional): add a repo *Variable* `STREAMLIT_APP_URL` =
   your app URL; `keep-alive.yml` pings it every 6 hours so it never sleeps.

## Reliability: dual data source

- **Primary:** Yahoo Finance (`yfinance`) for full history.
- **Fallback:** official **NSE Bhavcopy**. Every scan backs up whatever Yahoo
  returned into `data/price_history.parquet` and appends the latest authoritative
  EOD bar. If Yahoo is down/rate-limited, the scanner rebuilds from this store, so a
  Yahoo outage degrades gracefully instead of breaking the app. (The store needs one
  successful run to seed full history; it then stays current automatically.)

## Risk plan & backtest

- Each signal carries an **ATR-based stop-loss and target** (default 1.5×ATR stop,
  1:2 risk/reward) in the dashboard and the Excel **Trade Plan** sheet.
- `backtest.py` replays history bar-by-bar (no look-ahead) and reports win-rate,
  average win/loss and expectancy. It is a **simplified** simulation (ignores
  slippage, brokerage, taxes, gaps, liquidity) — directional, not a promise.

## Compliance & data terms

This is a rule-based **technical screener for education/research** — not investment
advice, not a recommendation, and **not** operated by a SEBI-registered Research
Analyst / Investment Adviser. No guarantee of returns. Yahoo data is used for
personal, non-commercial use; NSE Bhavcopy is used for personal/educational analysis
and is **not redistributed**. Full text in [`DISCLAIMER.md`](DISCLAIMER.md).

## Notes

- 13 of 294 names are unlisted/non-equity (NSDL, NSE, Fabindia, preference shares,
  AIFs) with no price data — flagged `tradable=N` and skipped.
- Trendline detection is heuristic; tune `pivot_window` / `trend_lookback` in the
  sidebar. Code is host-agnostic (also runs on Hugging Face Spaces, Render, or
  locally via Task Scheduler).
