"""
filters.py
----------
All screening filters applied to the scanner's results DataFrame.

Each filter is a small, pure function: (DataFrame, params) -> DataFrame.
This makes the UI layer trivial (just call the ones the user enabled) and
makes it easy to unit test or add new filters later without touching
Streamlit code.
"""

from __future__ import annotations

import pandas as pd

from utils import get_logger

logger = get_logger(__name__)

# The primary filter mandated by the project: only stocks trading above
# their 200-day EMA are shown by default.
def primary_ema200_filter(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only rows where Close > EMA200."""
    if df.empty:
        return df
    return df[df["Close"] > df["EMA200"]].copy()


def close_above_ema(df: pd.DataFrame, ema_col: str) -> pd.DataFrame:
    """Generic 'Close > EMA(n)' filter, e.g. ema_col='EMA20'."""
    if df.empty or ema_col not in df.columns:
        return df
    return df[df["Close"] > df[ema_col]].copy()


def ema_stack_bullish(df: pd.DataFrame) -> pd.DataFrame:
    """Keep rows where EMA20 > EMA50 > EMA100 > EMA200 (a clean bullish stack)."""
    if df.empty:
        return df
    mask = (df["EMA20"] > df["EMA50"]) & (df["EMA50"] > df["EMA100"]) & (df["EMA100"] > df["EMA200"])
    return df[mask].copy()


def rsi_above(df: pd.DataFrame, value: float) -> pd.DataFrame:
    """Keep rows where RSI14 > value."""
    if df.empty:
        return df
    return df[df["RSI14"] > value].copy()


def adx_above(df: pd.DataFrame, value: float) -> pd.DataFrame:
    """Keep rows where ADX14 > value (i.e. a strong trend, in either direction)."""
    if df.empty:
        return df
    return df[df["ADX14"] > value].copy()


def volume_above_average(df: pd.DataFrame) -> pd.DataFrame:
    """Keep rows where today's Volume exceeds the 20-day average volume."""
    if df.empty:
        return df
    return df[df["Volume"] > df["Vol_Avg20"]].copy()


def near_52_week_high(df: pd.DataFrame, threshold_pct: float = 5.0) -> pd.DataFrame:
    """Keep rows within ``threshold_pct``% of their 52-week high."""
    if df.empty:
        return df
    return df[df["High_52W_Dist_%"] >= -threshold_pct].copy()


def near_52_week_low(df: pd.DataFrame, threshold_pct: float = 5.0) -> pd.DataFrame:
    """Keep rows within ``threshold_pct``% of their 52-week low."""
    if df.empty:
        return df
    return df[df["Low_52W_Dist_%"] <= threshold_pct].copy()


def search_by_name(df: pd.DataFrame, query: str) -> pd.DataFrame:
    """Case-insensitive substring search on Company Name."""
    if df.empty or not query:
        return df
    return df[df["Company Name"].str.contains(query, case=False, na=False)].copy()


def search_by_symbol(df: pd.DataFrame, query: str) -> pd.DataFrame:
    """Case-insensitive substring search on Symbol."""
    if df.empty or not query:
        return df
    return df[df["Symbol"].str.contains(query, case=False, na=False)].copy()


def classify_ema200_zone(close: float, ema200: float, tolerance_pct: float = 1.0) -> str:
    """
    Classify a stock relative to its EMA200 for color coding.

    Returns one of: 'green', 'red', 'yellow'.
      - yellow: within `tolerance_pct`% of EMA200 (either side)
      - green:  Close > EMA200 (and outside the yellow band)
      - red:    Close < EMA200 (and outside the yellow band)
    """
    if ema200 in (None, 0) or close is None:
        return "red"
    diff_pct = ((close - ema200) / ema200) * 100.0
    if abs(diff_pct) <= tolerance_pct:
        return "yellow"
    return "green" if diff_pct > 0 else "red"
