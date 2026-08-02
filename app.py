"""
app.py
------
Streamlit entry point for the NSE Stock Scanner.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import streamlit as st

import filters as flt
from charts import build_detail_chart
from data import clear_cache
from scanner import RESULT_COLUMNS, StockScanner
from utils import DEFAULT_STOCKS_FILE, get_logger

logger = get_logger(__name__)

st.set_page_config(
    page_title="NSE Stock Scanner",
    page_icon="📈",
    layout="wide",
)

# --------------------------------------------------------------------------
# Session state initialization
# --------------------------------------------------------------------------
if "scan_results" not in st.session_state:
    st.session_state.scan_results = None  # full scan output (all stocks, all indicators)
if "scanner" not in st.session_state:
    st.session_state.scanner = None  # StockScanner instance (keeps history for detail charts)
if "selected_symbol" not in st.session_state:
    st.session_state.selected_symbol = None


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def style_ema200_zone(row: pd.Series) -> list[str]:
    """Row-level background color based on Close vs EMA200."""
    zone = flt.classify_ema200_zone(row["Close"], row["EMA200"])
    color_map = {
        "green": "background-color: #d9f2e6",
        "red": "background-color: #fbe1e1",
        "yellow": "background-color: #fff6d1",
    }
    return [color_map[zone]] * len(row)


def run_scan() -> None:
    """Execute a full scan with a live progress bar, storing results in session state."""
    scanner = StockScanner(stocks_csv=st.session_state.get("stocks_csv_path", DEFAULT_STOCKS_FILE))

    progress_bar = st.progress(0.0, text="Starting scan...")

    def _on_progress(completed: int, total: int, symbol: str) -> None:
        progress_bar.progress(completed / total, text=f"Scanned {completed}/{total} — {symbol}")

    with st.spinner("Downloading data and computing indicators..."):
        try:
            results = scanner.run_scan(max_workers=12, progress_callback=_on_progress)
        except FileNotFoundError as exc:
            st.error(str(exc))
            progress_bar.empty()
            return
        except ValueError as exc:
            st.error(str(exc))
            progress_bar.empty()
            return

    progress_bar.empty()
    st.session_state.scan_results = results
    st.session_state.scanner = scanner

    if results.empty:
        st.warning("Scan finished but no stocks returned valid data. Check your stocks.csv and network access.")
    else:
        st.success(f"Scan complete: {len(results)} stocks processed.")


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    """Serialize a DataFrame to an in-memory Excel (.xlsx) file."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Scan Results")
    return buffer.getvalue()


# --------------------------------------------------------------------------
# Sidebar: watchlist source + filters
# --------------------------------------------------------------------------
st.sidebar.title("📈 NSE Stock Scanner")

with st.sidebar.expander("Watchlist source", expanded=False):
    uploaded_file = st.file_uploader("Upload stocks.csv (optional)", type=["csv"])
    if uploaded_file is not None:
        tmp_path = Path("uploaded_stocks.csv")
        tmp_path.write_bytes(uploaded_file.getvalue())
        st.session_state.stocks_csv_path = str(tmp_path)
        st.caption(f"Using uploaded file ({uploaded_file.name})")
    else:
        st.session_state.stocks_csv_path = str(DEFAULT_STOCKS_FILE)
        st.caption(f"Using default: {DEFAULT_STOCKS_FILE.name}")

col_scan, col_clear = st.sidebar.columns(2)
scan_clicked = col_scan.button("🔍 Run Scan", use_container_width=True, type="primary")
if col_clear.button("🗑️ Clear Cache", use_container_width=True):
    n = clear_cache()
    st.sidebar.info(f"Cleared {n} cached files.")

st.sidebar.markdown("---")
st.sidebar.subheader("Filters")

filter_ema20 = st.sidebar.checkbox("Close > EMA20")
filter_ema50 = st.sidebar.checkbox("Close > EMA50")
filter_ema100 = st.sidebar.checkbox("Close > EMA100")
filter_ema200_only = st.sidebar.checkbox(
    "Close > EMA200 (primary filter)", value=True,
    help="This is the core scan criterion. Uncheck to see all scanned stocks.",
)
filter_stack = st.sidebar.checkbox("EMA20 > EMA50 > EMA100 > EMA200 (bullish stack)")

rsi_enabled = st.sidebar.checkbox("RSI greater than")
rsi_value = st.sidebar.slider("RSI threshold", 0, 100, 50, disabled=not rsi_enabled)

adx_enabled = st.sidebar.checkbox("ADX greater than")
adx_value = st.sidebar.slider("ADX threshold", 0, 100, 25, disabled=not adx_enabled)

filter_volume = st.sidebar.checkbox("Volume > 20-Day Average")

near_high_enabled = st.sidebar.checkbox("Near 52-Week High")
near_high_pct = st.sidebar.slider("Within % of 52W High", 0.0, 20.0, 5.0, disabled=not near_high_enabled)

near_low_enabled = st.sidebar.checkbox("Near 52-Week Low")
near_low_pct = st.sidebar.slider("Within % of 52W Low", 0.0, 20.0, 5.0, disabled=not near_low_enabled)

st.sidebar.markdown("---")
search_name = st.sidebar.text_input("Search by Company Name")
search_symbol = st.sidebar.text_input("Search by Symbol")


# --------------------------------------------------------------------------
# Main area
# --------------------------------------------------------------------------
st.title("NSE Stock Scanner — EMA200 Trend Screener")
st.caption(
    "Scans your custom watchlist and highlights stocks trading above their 200-day EMA, "
    "with additional technical filters."
)

if scan_clicked:
    run_scan()

results = st.session_state.scan_results

if results is None:
    st.info("👈 Configure filters and click **Run Scan** in the sidebar to begin.")
    st.stop()

if results.empty:
    st.warning("No results to display. Try running the scan again.")
    st.stop()

# --------------------------------------------------------------------------
# Apply filters
# --------------------------------------------------------------------------
filtered = results.copy()

if filter_ema200_only:
    filtered = flt.close_above_ema(filtered, "EMA200")
if filter_ema20:
    filtered = flt.close_above_ema(filtered, "EMA20")
if filter_ema50:
    filtered = flt.close_above_ema(filtered, "EMA50")
if filter_ema100:
    filtered = flt.close_above_ema(filtered, "EMA100")
if filter_stack:
    filtered = flt.ema_stack_bullish(filtered)
if rsi_enabled:
    filtered = flt.rsi_above(filtered, rsi_value)
if adx_enabled:
    filtered = flt.adx_above(filtered, adx_value)
if filter_volume:
    filtered = flt.volume_above_average(filtered)
if near_high_enabled:
    filtered = flt.near_52_week_high(filtered, near_high_pct)
if near_low_enabled:
    filtered = flt.near_52_week_low(filtered, near_low_pct)
if search_name:
    filtered = flt.search_by_name(filtered, search_name)
if search_symbol:
    filtered = flt.search_by_symbol(filtered, search_symbol)

filtered = filtered.sort_values("Dist_Above_EMA200_%", ascending=False).reset_index(drop=True)

st.subheader(f"Results ({len(filtered)} of {len(results)} scanned stocks)")

# --------------------------------------------------------------------------
# Results table (color-coded, click a row to open the detail page)
# --------------------------------------------------------------------------
display_df = filtered.rename(
    columns={
        "Dist_Above_EMA200_%": "Dist. Above EMA200 (%)",
        "RSI14": "RSI",
        "MACD_Signal": "MACD Signal",
        "MACD_Hist": "MACD Hist",
        "ADX14": "ADX",
        "Vol_Avg20": "20D Avg Volume",
        "High_52W_Dist_%": "52W High Dist (%)",
        "Low_52W_Dist_%": "52W Low Dist (%)",
        "Last_Updated": "As of",
    }
)

styled = display_df.style.apply(
    lambda row: style_ema200_zone(filtered.iloc[row.name]), axis=1
)

event = st.dataframe(
    styled,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    key="results_table",
)

st.caption("🟩 Above EMA200  🟥 Below EMA200  🟨 Within 1% of EMA200 — click a row to open its detail chart.")

# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------
exp_col1, exp_col2, _ = st.columns([1, 1, 4])
exp_col1.download_button(
    "⬇️ Export CSV",
    data=filtered.to_csv(index=False).encode("utf-8"),
    file_name="stock_scan_results.csv",
    mime="text/csv",
    use_container_width=True,
)
exp_col2.download_button(
    "⬇️ Export Excel",
    data=to_excel_bytes(filtered),
    file_name="stock_scan_results.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)

# --------------------------------------------------------------------------
# Detail page (triggered by row selection)
# --------------------------------------------------------------------------
selected_rows = event.selection.rows if event and event.selection else []
if selected_rows:
    selected_symbol = filtered.iloc[selected_rows[0]]["Symbol"]
    st.session_state.selected_symbol = selected_symbol

if st.session_state.selected_symbol:
    symbol = st.session_state.selected_symbol
    st.markdown("---")
    st.subheader(f"📊 Detail: {symbol}")

    history = st.session_state.scanner.get_history(symbol) if st.session_state.scanner else None
    if history is None or history.empty:
        st.warning("No detailed history available for this symbol. Try running the scan again.")
    else:
        fig = build_detail_chart(history, symbol)
        st.plotly_chart(fig, use_container_width=True)

        latest = history.iloc[-1]
        metric_cols = st.columns(6)
        metric_cols[0].metric("Close", f"{latest['Close']:.2f}")
        metric_cols[1].metric("EMA200", f"{latest['EMA200']:.2f}")
        metric_cols[2].metric("RSI(14)", f"{latest['RSI14']:.1f}")
        metric_cols[3].metric("ADX(14)", f"{latest['ADX14']:.1f}")
        metric_cols[4].metric("MACD", f"{latest['MACD']:.2f}")
        metric_cols[5].metric("Volume", f"{int(latest['Volume']):,}")
