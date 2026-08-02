"""
utils.py
--------
Shared utilities: logging configuration, small helper functions, and
constants used across the Stock Scanner application.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
BASE_DIR: Path = Path(__file__).resolve().parent
CACHE_DIR: Path = BASE_DIR / "cache"
LOG_DIR: Path = BASE_DIR / "logs"
DEFAULT_STOCKS_FILE: Path = BASE_DIR / "stocks.csv"

CACHE_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------
_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Create (or fetch) a configured logger that writes to both a rotating
    log file and stdout.

    Args:
        name: Logger name, typically ``__name__`` of the calling module.
        level: Logging level (default ``logging.INFO``).

    Returns:
        A configured ``logging.Logger`` instance.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        # Logger already configured (avoids duplicate handlers on reruns,
        # which matters a lot in Streamlit since scripts re-execute often).
        return logger

    logger.setLevel(level)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

    # Console handler
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    # File handler
    file_handler = logging.FileHandler(LOG_DIR / "stock_scanner.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logger.propagate = False
    return logger


# --------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------
def safe_round(value: float | None, decimals: int = 2) -> float | None:
    """Round a numeric value while gracefully handling ``None``/``NaN``."""
    if value is None:
        return None
    try:
        import math

        if isinstance(value, float) and math.isnan(value):
            return None
        return round(float(value), decimals)
    except (TypeError, ValueError):
        return None


def pct_change(current: float, reference: float) -> float | None:
    """
    Percentage difference of ``current`` relative to ``reference``.

    Example: pct_change(110, 100) -> 10.0  (10% above reference)
    """
    if reference in (None, 0) or current is None:
        return None
    try:
        return ((current - reference) / reference) * 100.0
    except (TypeError, ZeroDivisionError):
        return None


def ensure_ns_suffix(symbol: str) -> str:
    """
    Ensure an NSE ticker has the Yahoo Finance ``.NS`` suffix.

    Yahoo Finance requires NSE-listed tickers to be suffixed with ``.NS``
    (e.g. ``TCS.NS``). This helper normalizes user-entered symbols that may
    be missing the suffix.
    """
    symbol = symbol.strip().upper()
    if not symbol:
        return symbol
    if symbol.endswith(".NS") or symbol.endswith(".BO"):
        return symbol
    return f"{symbol}.NS"


def chunk_list(items: list, chunk_size: int) -> list[list]:
    """Split a list into consecutive chunks of at most ``chunk_size`` items."""
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]
