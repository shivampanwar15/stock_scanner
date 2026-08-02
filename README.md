# NSE Stock Scanner

A production-quality Streamlit application that scans a custom watchlist of
NSE stocks and identifies which ones are trading above their 200-day EMA
(EMA200), with a full suite of additional technical filters, an interactive
candlestick detail page, and CSV/Excel export.

---

## 1. Project Structure

```
stock_scanner/
│── app.py            # Streamlit UI (entry point)
│── scanner.py         # Orchestrates the scan (data -> indicators -> results table)
│── indicators.py       # EMA, RSI, MACD, ADX, 52W high/low, volume avg
│── data.py            # yfinance downloads, multithreading, disk caching
│── filters.py          # All screening filters (EMA, RSI, ADX, volume, 52W, search)
│── charts.py           # Plotly candlestick + RSI/MACD/Volume detail chart
│── utils.py            # Logging, formatting helpers, path constants
│── requirements.txt
│── stocks.csv           # Your watchlist (edit this!)
│── cache/              # Auto-created; cached OHLCV data (parquet)
│── logs/               # Auto-created; application logs
```

## 2. Installation

Requires Python 3.12+.

```bash
cd stock_scanner
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Running the app

```bash
streamlit run app.py
```

This opens the app in your browser (default: http://localhost:8501).

## 4. Editing your watchlist

Edit `stocks.csv` directly — it needs exactly two columns:

```csv
Company Name,Symbol
Tata Consultancy Services,TCS.NS
Infosys,INFY.NS
```

**Important — ticker format:** Yahoo Finance requires NSE symbols to be
suffixed with `.NS` (e.g. `RELIANCE.NS`, `HDFCBANK.NS`). If you only have
the plain NSE symbol, add `.NS` to it in the CSV. (BSE symbols use `.BO`
instead, if you ever need them — the app doesn't require this but
`utils.ensure_ns_suffix()` is there if you extend the app to accept
raw symbols.)

You can also upload a different CSV at runtime from the sidebar
("Watchlist source" → "Upload stocks.csv") without editing the file on
disk — useful for testing a different list without losing your main one.

## 5. How a scan works

1. Click **Run Scan** in the sidebar.
2. The app downloads ~700 calendar days of daily OHLCV data per symbol
   from Yahoo Finance (enough to guarantee 400+ trading days for an
   accurate EMA200), using up to 12 concurrent threads.
3. Each symbol's data is cached to `cache/<SYMBOL>.parquet` for 12 hours,
   so re-running a scan the same day is near-instant for unchanged
   symbols. Use **Clear Cache** in the sidebar to force fresh downloads.
4. Indicators (EMA20/50/100/200, RSI14, MACD, ADX14, 20-day avg volume,
   52-week high/low) are computed for every symbol.
5. By default, only stocks with **Close > EMA200** are shown (the primary
   filter) — uncheck it in the sidebar to see every scanned stock.
6. Additional filters in the sidebar can be combined freely (all are
   AND'ed together).

## 6. Reading the results table

- **Row color**: 🟩 green = Close > EMA200, 🟥 red = Close < EMA200,
  🟨 yellow = within 1% of EMA200.
- **Sort order**: highest "Distance Above EMA200 (%)" first.
- **Click a row** to open the detail page below the table: a candlestick
  chart with EMA20/50/100/200 overlays, volume, RSI, and MACD panels.

## 7. Exporting results

Use the **Export CSV** / **Export Excel** buttons above the table. Exports
reflect whatever filters are currently active (i.e. exactly what's on
screen).

## 8. Performance notes

- Scanning ~150 stocks typically completes in well under a minute on a
  normal broadband connection, thanks to threaded downloads
  (`data.download_watchlist_data`, `max_workers=12` by default — tune
  this in `app.py`'s `run_scan()` if Yahoo starts rate-limiting you).
- Failed downloads (delisted tickers, temporary network errors, etc.) are
  logged and skipped — they don't abort the whole scan. Check
  `logs/stock_scanner.log` for details on any symbol that didn't load.

## 9. Why no `pandas-ta` / `ta` dependency?

The original spec listed `pandas-ta` or `ta` as candidate libraries.
Both have a history of breaking against newer numpy/pandas releases and
`pandas-ta` in particular has been effectively unmaintained. To keep the
project robust and dependency-light, all indicators (`indicators.py`) are
implemented directly with pandas/numpy using the standard, well-documented
formulas (Wilder's smoothing for RSI and ADX, standard EMA-based MACD) —
so results match TradingView and most other charting platforms. If you'd
prefer to swap in a library later, `indicators.py` is the only file that
needs to change; every function signature (`ema`, `rsi`, `macd`, `adx`,
etc.) can be re-implemented on top of `pandas-ta`/`ta` without touching
`scanner.py`, `app.py`, or anything else.

## 10. Extending the scanner

The architecture is deliberately modular so new features are additive:

| To add...                          | Do this                                                                 |
|-------------------------------------|--------------------------------------------------------------------------|
| A new indicator (Supertrend, VWAP, Bollinger Bands, ATR, etc.) | Add a function to `indicators.py`, call it from `compute_all_indicators()`, add its column to `scanner.RESULT_COLUMNS` / `_build_row()` |
| A new filter                       | Add a function to `filters.py`, wire a sidebar control to it in `app.py` |
| Sector-wise analysis                | Add a `Sector` column to `stocks.csv`, group in `scanner.py`             |
| Relative Strength Ranking           | Add an index/benchmark fetch in `data.py`, compute ratio in `indicators.py` |
| Index comparison                    | Fetch `^NSEI` (Nifty 50) via `data.py`, overlay in `charts.py`           |
| Backtesting                        | New `backtest.py` module consuming `scanner.get_history()`               |
| Portfolio tracker                  | New `portfolio.py` + a Streamlit page/tab                                |
| Telegram / Email alerts             | New `alerts.py` triggered after `run_scan()` in `app.py`                 |
| Daily auto-scan after market close  | Wrap `StockScanner().run_scan()` in a scheduled script (cron / `schedule` lib) run headless, writing results to disk or triggering alerts.py |

## 11. Troubleshooting

- **"No data returned for SYMBOL"**: check the symbol has the correct
  `.NS` suffix and is actively traded; delisted/renamed tickers will fail.
- **Slow first scan**: the first run for any symbol always hits the
  network (nothing cached yet); subsequent scans same-day are much faster.
- **Rate limiting from Yahoo Finance**: lower `max_workers` in
  `app.py`'s `run_scan()` call to `StockScanner.run_scan()`.
- **Streamlit row-click selection not working**: row selection requires
  Streamlit ≥ 1.36 (see `requirements.txt`) — upgrade with
  `pip install -U streamlit` if you're on an older version.
