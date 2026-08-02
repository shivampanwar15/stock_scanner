"""
scanner.py
----------
Top-level orchestration: load watchlist -> download data -> compute
indicators -> build the results table used by the Streamlit UI.
"""

from __future__ import annotations

from typing import Callable

import pandas as pd

from data import StockRef, download_watchlist_data, load_watchlist
from indicators import compute_all_indicators
from utils import DEFAULT_STOCKS_FILE, get_logger, pct_change, safe_round

logger = get_logger(__name__)

# Columns shown/exported, in display order.
RESULT_COLUMNS = [
    "Company Name",
    "Symbol",
    "Close",
    "EMA20",
    "EMA50",
    "EMA100",
    "EMA200",
    "Dist_Above_EMA200_%",
    "RSI14",
    "MACD",
    "MACD_Signal",
    "MACD_Hist",
    "ADX14",
    "Volume",
    "Vol_Avg20",
    "High_52W_Dist_%",
    "Low_52W_Dist_%",
    "Last_Updated",
]


class StockScanner:
    """
    Encapsulates a full scan run over a watchlist.

    Usage:
        scanner = StockScanner()
        results_df = scanner.run_scan()
    """

    def __init__(self, stocks_csv: str = DEFAULT_STOCKS_FILE) -> None:
        self.stocks_csv = stocks_csv
        self._raw_data: dict[str, pd.DataFrame] = {}
        self._enriched_data: dict[str, pd.DataFrame] = {}
        self.watchlist: list[StockRef] = []

    def run_scan(
        self,
        max_workers: int = 12,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> pd.DataFrame:
        """
        Run a full scan: download data for every watchlist symbol, compute
        indicators, and return one row per stock with the latest values.

        Note: this returns ALL scanned stocks (with indicator values). The
        "Close > EMA200" primary filter is applied separately in
        ``filters.py`` / the UI layer, so the raw scan results remain
        reusable for other filters too.

        Args:
            max_workers: Concurrent download threads.
            progress_callback: Optional ``(completed, total, symbol)`` hook
                for progress bars.

        Returns:
            DataFrame with one row per successfully-scanned stock.
        """
        self.watchlist = load_watchlist(self.stocks_csv)
        symbols = [s.symbol for s in self.watchlist]
        name_by_symbol = {s.symbol: s.company_name for s in self.watchlist}

        self._raw_data = download_watchlist_data(
            symbols, max_workers=max_workers, progress_callback=progress_callback
        )

        rows: list[dict] = []
        for symbol, ohlcv in self._raw_data.items():
            try:
                enriched = compute_all_indicators(ohlcv)
                self._enriched_data[symbol] = enriched
                row = self._build_row(symbol, name_by_symbol.get(symbol, symbol), enriched)
                if row is not None:
                    rows.append(row)
            except Exception as exc:  # noqa: BLE001 - one bad symbol shouldn't kill the scan
                logger.error("Failed to compute indicators for %s: %s", symbol, exc)

        if not rows:
            logger.warning("Scan produced zero valid rows")
            return pd.DataFrame(columns=RESULT_COLUMNS)

        df = pd.DataFrame(rows)
        df = df.sort_values("Dist_Above_EMA200_%", ascending=False).reset_index(drop=True)
        logger.info("Scan complete: %d stocks with valid indicators", len(df))
        return df

    @staticmethod
    def _build_row(symbol: str, company_name: str, enriched: pd.DataFrame) -> dict | None:
        """Extract the latest indicator values for one stock as a flat dict."""
        if enriched.empty:
            return None

        latest = enriched.iloc[-1]

        # Require EMA200 to be a real (non-NaN) value; otherwise we don't
        # have enough history for a trustworthy reading.
        if pd.isna(latest.get("EMA200")):
            logger.warning("Skipping %s: EMA200 not available (insufficient history)", symbol)
            return None

        close = float(latest["Close"])
        ema200 = float(latest["EMA200"])

        return {
            "Company Name": company_name,
            "Symbol": symbol,
            "Close": safe_round(close),
            "EMA20": safe_round(latest.get("EMA20")),
            "EMA50": safe_round(latest.get("EMA50")),
            "EMA100": safe_round(latest.get("EMA100")),
            "EMA200": safe_round(ema200),
            "Dist_Above_EMA200_%": safe_round(pct_change(close, ema200)),
            "RSI14": safe_round(latest.get("RSI14")),
            "MACD": safe_round(latest.get("MACD"), 3),
            "MACD_Signal": safe_round(latest.get("MACD_Signal"), 3),
            "MACD_Hist": safe_round(latest.get("MACD_Hist"), 3),
            "ADX14": safe_round(latest.get("ADX14")),
            "Volume": int(latest["Volume"]) if pd.notna(latest["Volume"]) else None,
            "Vol_Avg20": (
                int(latest["Vol_Avg20"]) if pd.notna(latest.get("Vol_Avg20")) else None
            ),
            "High_52W_Dist_%": safe_round(pct_change(close, latest.get("High_52W"))),
            "Low_52W_Dist_%": safe_round(pct_change(close, latest.get("Low_52W"))),
            "Last_Updated": enriched.index[-1].strftime("%Y-%m-%d"),
        }

    def get_history(self, symbol: str) -> pd.DataFrame | None:
        """Return the full enriched OHLCV+indicator history for one symbol (for the detail chart)."""
        return self._enriched_data.get(symbol)
