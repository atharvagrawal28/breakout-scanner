"""
app.py — Streamlit dashboard for the Stock Breakout Scanner.

Run locally:   streamlit run app.py
Deploy:        push to GitHub -> Streamlit Community Cloud (see README).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import scanner
import export

# --------------------------------------------------------------------------- #
# Branding — edit these two lines only.                                        #
# --------------------------------------------------------------------------- #
AUTHOR = "Atharv Agrawal"
LINKEDIN_URL = "https://www.linkedin.com/in/atharv-agrawal-295743233"

st.set_page_config(page_title="Stock Breakout Scanner", page_icon="📈", layout="wide")

RESULTS = Path(__file__).parent / "results"


# ----------------------------- educational content ----------------------------- #
FRAMEWORK_INTRO = (
    "Our scanner looks for stocks that are **starting a fresh up-move after a "
    "downtrend** — a high-probability breakout. A stock must pass **all 5 checks "
    "below** to qualify as a Signal. Stocks passing 3–4 appear on the Watchlist "
    "(setups still forming)."
)

CONDITIONS_SHORT = [
    "1️⃣  RSI(14) between 50 and 65 — healthy momentum, not overbought",
    "2️⃣  Price above DEMA 20 / 50 / 100 / 200 — uptrend on every timeframe",
    "3️⃣  Volume above its 10-day average — real buying participation",
    "4️⃣  Descending-trendline breakout — price closes above falling resistance",
    "5️⃣  Successful retest — price came back to the line and held above it",
]

CONDITION_DETAILS = {
    "1 · RSI (14) between 50 and 65": (
        "**What it is:** RSI (Relative Strength Index) measures momentum on a 0–100 "
        "scale over the last 14 days.\n\n"
        "**Why 50–65:** Above 50 means buyers are in control (bullish momentum). "
        "We cap it at 65 so we don't chase stocks that are already **overbought** "
        "(RSI > 70 often means the move is stretched and due for a pullback). "
        "50–65 is the sweet spot: real strength, with room left to run."
    ),
    "2 · Price above all DEMAs": (
        "**What it is:** DEMA (Double Exponential Moving Average) is a smoother, "
        "faster-reacting trend line than a normal moving average — it hugs price "
        "with less lag.\n\n"
        "**Why all four (20/50/100/200):** When price is above the short (20), "
        "medium (50, 100) *and* long-term (200) DEMAs at once, the trend is up on "
        "**every** horizon — short-term traders and long-term investors are all "
        "on the buy side. This filters out weak, choppy stocks."
    ),
    "3 · Volume > 10-day average": (
        "**What it is:** We compare today's volume to the average of the last 10 "
        "trading days.\n\n"
        "**Why it matters:** A breakout on **low** volume is suspect — it can be a "
        "fake-out. Volume above the 10-day average means the move has genuine "
        "participation and conviction behind it, which makes it more likely to hold."
    ),
    "4 · Descending-trendline breakout": (
        "**What it is:** We connect a stock's recent **falling swing highs** into a "
        "downward-sloping resistance line. As long as price keeps making lower "
        "highs, sellers are in control.\n\n"
        "**The breakout:** When price finally **closes above** that line, it signals "
        "sellers are losing grip and the downtrend may be reversing — the classic "
        "first sign of a new up-move."
    ),
    "5 · Successful retest": (
        "**What it is:** After breaking above the trendline, strong stocks often dip "
        "back down to **touch** the old resistance line — which now flips to act as "
        "**support** — and then bounce off it.\n\n"
        "**Why we require it:** A held retest is the market *confirming* the "
        "breakout was real. It dramatically reduces false signals. A stock that "
        "broke out but hasn't retested yet sits on the Watchlist until it does."
    ),
}


# ----------------------------- optional password ----------------------------- #
def check_password() -> bool:
    pw = None
    try:
        pw = st.secrets.get("app_password", None)
    except Exception:
        pw = None
    if not pw:
        return True
    if st.session_state.get("auth_ok"):
        return True
    st.title("📈 Stock Breakout Scanner")
    entered = st.text_input("Enter password", type="password")
    if entered:
        if entered == pw:
            st.session_state["auth_ok"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False


if not check_password():
    st.stop()


# ----------------------------- data helpers ----------------------------- #
@st.cache_data(show_spinner=False)
def load_universe():
    return scanner.load_universe()


def load_cached_results():
    p = RESULTS / "latest.parquet"
    if p.exists():
        try:
            df = pd.read_parquet(p)
            ts = (RESULTS / "last_run.txt").read_text().strip() if (RESULTS / "last_run.txt").exists() else "?"
            return df, ts
        except Exception:
            return None, None
    return None, None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_one(ticker: str):
    h = scanner.download_history([ticker], batch_size=1)
    return h.get(ticker)

# ----------------------------- refresh schedule ----------------------------- #
# Mirrors .github/workflows/daily-scan.yml (cron "15 3 * * 1-5" = 08:45 IST, Mon-Fri).
SCAN_HOUR_IST, SCAN_MIN_IST = 8, 45


def next_refresh_ist():
    from datetime import datetime, timedelta, timezone
    ist = timezone(timedelta(hours=5, minutes=30))
    now = datetime.now(ist)
    run = now.replace(hour=SCAN_HOUR_IST, minute=SCAN_MIN_IST, second=0, microsecond=0)
    if now >= run:
        run = run + timedelta(days=1)
    while run.weekday() >= 5:           # skip Sat/Sun
        run = run + timedelta(days=1)
    delta = run - now
    hrs = int(delta.total_seconds() // 3600)
    mins = int((delta.total_seconds() % 3600) // 60)
    return run, f"{hrs}h {mins}m"



# ----------------------------- sidebar ----------------------------- #
st.sidebar.title("📈 Breakout Scanner")

with st.sidebar.expander("📚 Our breakout framework", expanded=True):
    st.markdown(FRAMEWORK_INTRO)
    st.markdown("**The 5 checks:**")
    for c in CONDITIONS_SHORT:
        st.markdown("- " + c)

with st.sidebar.expander("ℹ️ Learn about each condition", expanded=False):
    pick = st.selectbox("Pick a condition to understand it",
                        list(CONDITION_DETAILS.keys()))
    st.info(CONDITION_DETAILS[pick])

with st.sidebar.expander("⚠️ Disclaimer & data sources", expanded=False):
    st.markdown(
        "**Educational technical screener — not investment advice** and not a "
        "stock recommendation. Not provided by a SEBI-registered Research Analyst "
        "or Investment Adviser.\n\n"
        "Signals are rule-based screens on historical data; no guarantee of "
        "accuracy or returns. **Past performance does not guarantee future "
        "results** and trading involves risk of loss. Always do your own research "
        "and consult a SEBI-registered adviser before trading.\n\n"
        "**Data:** Yahoo Finance (yfinance) for personal use, with NSE official "
        "Bhavcopy as a free fallback. Not affiliated with Yahoo or NSE."
    )

st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ Scan settings")
st.sidebar.caption("Defaults match the standard framework. Adjust only if needed.")

params = {
    "rsi_low": st.sidebar.slider("RSI lower bound", 30.0, 60.0, 50.0, 1.0),
    "rsi_high": st.sidebar.slider("RSI upper bound", 55.0, 80.0, 65.0, 1.0),
    "trend_lookback": st.sidebar.slider("Trendline lookback (days)", 40, 150, 90, 5),
    "pivot_window": st.sidebar.slider("Swing-high sensitivity", 2, 6, 3, 1),
    "breakout_lookback": st.sidebar.slider("Breakout recency (days)", 5, 30, 15, 1),
    "retest_tol": st.sidebar.slider("Retest tolerance (%)", 0.5, 3.0, 1.5, 0.1) / 100.0,
}
wl_min = st.sidebar.slider("Watchlist minimum score", 2, 4, 3, 1)

st.sidebar.markdown("---")
st.sidebar.caption("Data: Yahoo Finance (free, ~15-min delayed). Not investment advice.")


# ----------------------------- header ----------------------------- #
st.title("📈 Stock Breakout Scanner")
st.caption("294-stock universe · RSI · DEMA stack · volume · descending-trendline "
           "breakout + retest")

cached, cached_ts = load_cached_results()

col_a, col_b, col_c = st.columns([1, 1, 2])
run = col_a.button("🔍 Run Live Scan", type="primary", use_container_width=True)
if cached is not None:
    col_b.metric("Last auto-scan", cached_ts)
col_c.caption("‘Run Live Scan’ pulls fresh data now (~1–3 min). The auto-scan "
              "(GitHub Actions) refreshes results every morning.")

_next_run, _eta = next_refresh_ist()
st.caption(
    f"🔄 **Next automatic refresh:** {_next_run:%a %d %b %Y, %I:%M %p} IST "
    f"(in ~{_eta}). Runs every weekday ~08:45 AM IST, before market open, on the "
    "previous trading day’s close. You can also press **Run Live Scan** anytime."
)


def do_scan():
    prog = st.progress(0.0, text="Starting...")
    status = st.empty()

    def pcb(done, total):
        prog.progress(min(done / total, 1.0), text=f"Downloaded {done}/{total} stocks")

    def scb(msg):
        status.write(msg)

    df = scanner.run_scan(load_universe(), params=params,
                          progress_cb=pcb, status_cb=scb)
    prog.empty(); status.empty()
    return df


if run:
    with st.spinner("Scanning all stocks..."):
        scan_df = do_scan()
        st.session_state["scan_df"] = scan_df
        st.session_state["scan_ts"] = datetime.now().strftime("%Y-%m-%d %H:%M")
elif "scan_df" not in st.session_state and cached is not None:
    st.session_state["scan_df"] = cached
    st.session_state["scan_ts"] = cached_ts

scan_df = st.session_state.get("scan_df")


def render_footer():
    st.markdown("---")
    st.markdown(
        f"""
        <div style="text-align:center; padding:10px 0; color:#555; font-size:0.9rem;">
            Built by <b>{AUTHOR}</b> &nbsp;·&nbsp;
            <a href="{LINKEDIN_URL}" target="_blank" style="text-decoration:none; color:#0A66C2;">
                🔗 LinkedIn
            </a>
            <br>
            <span style="font-size:0.8rem; color:#888;">
                Educational tool — technical screens, not investment advice. Always verify before trading.
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )


if scan_df is None or len(scan_df) == 0:
    st.info("No results yet. Click **Run Live Scan** to scan all stocks, "
            "or wait for the morning auto-scan to populate results.")
    render_footer()
    st.stop()

if "_passes_all" not in scan_df.columns:
    scan_df = scan_df.copy()
    scan_df["_passes_all"] = scan_df["Score"] == 5

sig = scanner.signals_only(scan_df) if "_passes_all" in scan_df.columns else pd.DataFrame()
wl = scanner.watchlist(scan_df, min_score=wl_min) if "Score" in scan_df.columns else pd.DataFrame()

# Data date = the last completed (EOD) bar the scan used
data_date = "—"
if "Data Date" in scan_df.columns and len(scan_df):
    try:
        data_date = scan_df["Data Date"].mode().iloc[0]
    except Exception:
        data_date = str(scan_df["Data Date"].iloc[0])

m1, m2, m3, m4 = st.columns(4)
m1.metric("Stocks evaluated", len(scan_df))
m2.metric("✅ Strict signals", len(sig))
m3.metric("👀 Watchlist", len(wl))
m4.metric("📅 Data as of (EOD)", data_date)

st.info(
    "ℹ️ **‘Current Price’ is the last completed daily close (end-of-day), not a live "
    f"intraday price.** Prices/volumes are as of the close on **{data_date}**. Today’s "
    "in-progress candle is excluded so signals use only finalised data. "
    "Figures tie exactly to the NSE official Bhavcopy.",
    icon="📌",
)

xlsx = export.build_workbook(scan_df, run_dt=datetime.now())
st.download_button("⬇️ Download Excel report", data=xlsx,
                   file_name=f"breakout_scan_{datetime.now():%Y-%m-%d}.xlsx",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

tab1, tab2, tab3 = st.tabs([f"✅ Signals ({len(sig)})",
                            f"👀 Watchlist ({len(wl)})",
                            "📊 Chart inspector"])

with tab1:
    st.subheader("Strict signals — all 5 conditions met")
    if sig.empty:
        st.info("No stocks passed all 5 conditions in this scan. "
                "Check the Watchlist — those are setups forming.")
    else:
        st.dataframe(sig, use_container_width=True, hide_index=True)

with tab2:
    st.subheader("Watchlist — setups forming (3–4 of 5)")
    st.caption("‘Missing’ shows the remaining condition(s). A stock with only "
               "‘Retest held’ missing has already broken out and is awaiting the retest.")
    if wl.empty:
        st.info("No near-misses at the current threshold.")
    else:
        st.dataframe(wl, use_container_width=True, hide_index=True)

with tab3:
    st.subheader("Inspect a stock")
    options = scan_df.sort_values("Score", ascending=False)
    label = options.apply(lambda r: f"{r['Symbol']} — {r['Company Name']} (score {r['Score']})", axis=1)
    choice = st.selectbox("Pick a stock", options.index, format_func=lambda i: label.loc[i])
    row = scan_df.loc[choice]
    ticker = f"{row['Symbol']}.NS"

    c = st.columns(5)
    c[0].metric("Price", row["Current Price"])
    c[1].metric("RSI", row["RSI"])
    c[2].metric("Vol ratio", row["Volume Ratio"])
    c[3].metric("Breakout", row["Trendline Breakout"])
    c[4].metric("Retest", row["Retest Confirmed"])

    with st.spinner("Loading chart..."):
        hist = fetch_one(ticker)
    if hist is None or len(hist) < scanner.MIN_BARS:
        st.warning("Could not load price history for the chart.")
    else:
        import plotly.graph_objects as go
        df = hist.dropna().copy()
        view = df.iloc[-180:]
        d20 = scanner.dema(df["Close"], 20).iloc[-180:]
        d50 = scanner.dema(df["Close"], 50).iloc[-180:]
        d200 = scanner.dema(df["Close"], 200).iloc[-180:]
        tl = scanner.detect_trendline(df, lookback=params["trend_lookback"],
                                      pivot_window=params["pivot_window"],
                                      breakout_lookback=params["breakout_lookback"],
                                      retest_tol=params["retest_tol"])

        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=view.index, open=view["Open"], high=view["High"],
                                     low=view["Low"], close=view["Close"], name="Price"))
        fig.add_trace(go.Scatter(x=view.index, y=d20, name="DEMA20", line=dict(width=1)))
        fig.add_trace(go.Scatter(x=view.index, y=d50, name="DEMA50", line=dict(width=1)))
        fig.add_trace(go.Scatter(x=view.index, y=d200, name="DEMA200", line=dict(width=1)))

        if tl.p1_idx is not None and not pd.isna(tl.slope):
            y1 = df["High"].iloc[tl.p1_idx]
            xs = view.index
            offsets = [df.index.get_loc(x) - tl.p1_idx for x in xs]
            ys = [y1 + tl.slope * o for o in offsets]
            fig.add_trace(go.Scatter(x=xs, y=ys, name="Trendline",
                                     line=dict(color="orange", dash="dash", width=2)))
        if tl.breakout_idx is not None and tl.breakout_idx >= len(df) - 180:
            bx = df.index[tl.breakout_idx]
            fig.add_trace(go.Scatter(x=[bx], y=[df["Close"].iloc[tl.breakout_idx]],
                                     mode="markers", name="Breakout",
                                     marker=dict(symbol="triangle-up", size=14, color="green")))
        fig.update_layout(height=520, xaxis_rangeslider_visible=False,
                          margin=dict(l=10, r=10, t=30, b=10),
                          legend=dict(orientation="h", y=1.02, yanchor="bottom"))
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"Trendline level now: {tl.line_now:.2f} · "
                   f"Breakout: {'Yes' if tl.has_breakout else 'No'} · "
                   f"Retest: {'Yes' if tl.retest_confirmed else 'No'}")

render_footer()
