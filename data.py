"""
data.py
-------
Handles all interaction with Yahoo Finance (via ``yfinance``): loading the
watchlist, downloading OHLCV history for each symbol, and caching results
on disk so repeated scans within the same trading day are fast.
"""

from __future__ import annotations

import datetime as dt
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd
import yfinance as yf

from utils import CACHE_DIR, DEFAULT_STOCKS_FILE, get_logger

logger = get_logger(__name__)

# Minimum number of trading days of history required for a reliable EMA200.
MIN_TRADING_DAYS = 400

# How many symbols to download concurrently. yfinance / Yahoo will start
# throttling or rejecting requests if this is set too high.
DEFAULT_MAX_WORKERS = 12

# Cache entries older than this many hours are considered stale and are
# re-downloaded. 12 hours comfortably covers "once per trading day".
CACHE_TTL_HOURS = 12


@dataclass(frozen=True)
class StockRef:
    """A single row from stocks.csv: a company name paired with its ticker."""

    company_name: str
    symbol: str


def load_watchlist(csv_path: Path | str = DEFAULT_STOCKS_FILE) -> list[StockRef]:
    """
    Load the watchlist of stocks to scan from a CSV file.

    Expected columns: ``Company Name``, ``Symbol``.

    Args:
        csv_path: Path to the watchlist CSV file.

    Returns:
        A list of :class:`StockRef` objects.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
        ValueError: If required columns are missing.
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Watchlist file not found: {csv_path}. "
            "Create a stocks.csv with columns 'Company Name,Symbol'."
        )

    df = pd.read_csv(csv_path)
    df.columns = [c.strip() for c in df.columns]

    required_cols = {"Company Name", "Symbol"}
    if not required_cols.issubset(set(df.columns)):
        raise ValueError(
            f"stocks.csv must contain columns {required_cols}, found {list(df.columns)}"
        )

    df = df.dropna(subset=["Symbol"]).drop_duplicates(subset=["Symbol"])

    watchlist = [
        StockRef(company_name=str(row["Company Name"]).strip(), symbol=str(row["Symbol"]).strip())
        for _, row in df.iterrows()
    ]
    logger.info("Loaded %d stocks from watchlist %s", len(watchlist), csv_path)
    return watchlist


def _cache_path(symbol: str) -> Path:
    safe_symbol = symbol.replace("/", "_")
    return CACHE_DIR / f"{safe_symbol}.parquet"


def _is_cache_fresh(cache_file: Path) -> bool:
    """A cache file is fresh if it was written within CACHE_TTL_HOURS."""
    if not cache_file.exists():
        return False
    age_hours = (time.time() - cache_file.stat().st_mtime) / 3600.0
    return age_hours < CACHE_TTL_HOURS


def _read_cache(symbol: str) -> pd.DataFrame | None:
    cache_file = _cache_path(symbol)
    if _is_cache_fresh(cache_file):
        try:
            return pd.read_parquet(cache_file)
        except Exception as exc:  # noqa: BLE001 - cache corruption should never crash a scan
            logger.warning("Failed to read cache for %s: %s", symbol, exc)
    return None


def _write_cache(symbol: str, df: pd.DataFrame) -> None:
    try:
        df.to_parquet(_cache_path(symbol))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to write cache for %s: %s", symbol, exc)


def _download_single(symbol: str, period: str = "700d", interval: str = "1d") -> pd.DataFrame | None:
    """
    Download OHLCV history for a single symbol from Yahoo Finance.

    A period of ~700 calendar days is requested to guarantee at least
    MIN_TRADING_DAYS trading sessions (accounting for weekends/holidays).

    Returns:
        A DataFrame indexed by date with columns
        [Open, High, Low, Close, Volume], or ``None`` on failure.
    """
    cached = _read_cache(symbol)
    if cached is not None and len(cached) >= MIN_TRADING_DAYS:
        return cached

    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, interval=interval, auto_adjust=True)

        if hist is None or hist.empty:
            logger.warning("No data returned for %s", symbol)
            return None

        hist = hist[["Open", "High", "Low", "Close", "Volume"]].dropna()
        hist.index.name = "Date"

        if len(hist) < 50:
            logger.warning("Insufficient history for %s (%d rows)", symbol, len(hist))
            return None

        _write_cache(symbol, hist)
        return hist

    except Exception as exc:  # noqa: BLE001 - one bad symbol must not abort the whole scan
        logger.error("Failed to download %s: %s", symbol, exc)
        return None


def download_watchlist_data(
    symbols: list[str],
    max_workers: int = DEFAULT_MAX_WORKERS,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> dict[str, pd.DataFrame]:
    """
    Download OHLCV history for many symbols concurrently.

    Args:
        symbols: List of Yahoo Finance ticker symbols (e.g. ``TCS.NS``).
        max_workers: Number of concurrent download threads.
        progress_callback: Optional callable ``(completed, total, symbol)``
            invoked after each symbol finishes, useful for driving a
            Streamlit progress bar.

    Returns:
        Dict mapping symbol -> OHLCV DataFrame. Symbols that failed to
        download are simply omitted from the result (and logged).
    """
    results: dict[str, pd.DataFrame] = {}
    total = len(symbols)
    completed = 0

    logger.info("Starting download of %d symbols with %d workers", total, max_workers)
    start = time.time()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_symbol = {executor.submit(_download_single, sym): sym for sym in symbols}

        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            completed += 1
            try:
                df = future.result()
                if df is not None:
                    results[symbol] = df
            except Exception as exc:  # noqa: BLE001
                logger.error("Unexpected error downloading %s: %s", symbol, exc)

            if progress_callback:
                progress_callback(completed, total, symbol)

    elapsed = time.time() - start
    logger.info(
        "Download complete: %d/%d symbols succeeded in %.1fs",
        len(results),
        total,
        elapsed,
    )
    return results


def clear_cache() -> int:
    """Delete all cached parquet files. Returns the number of files removed."""
    count = 0
    for f in CACHE_DIR.glob("*.parquet"):
        f.unlink(missing_ok=True)
        count += 1
    logger.info("Cleared %d cache files", count)
    return count


def last_trading_date(df: pd.DataFrame) -> dt.date | None:
    """Return the most recent date present in an OHLCV DataFrame."""
    if df is None or df.empty:
        return None
    return df.index[-1].date()
