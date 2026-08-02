"""
indicators.py
-------------
Technical indicator calculations.

Design note: indicators are implemented directly with pandas/numpy rather
than depending on ``pandas-ta`` (which has had repeated breakage against
newer numpy/pandas releases and has been unmaintained). This keeps the
project dependency-light and avoids surprise breakage. Every formula below
follows the standard, widely-used definition (Wilder's smoothing for
RSI/ADX, standard EMA-based MACD), so results will match TradingView /
most charting platforms.

All functions take/return ``pandas.Series`` or a full OHLCV
``pandas.DataFrame`` and are pure (no side effects), which keeps them easy
to unit test and to extend with new indicators later.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from utils import get_logger

logger = get_logger(__name__)


# --------------------------------------------------------------------------
# Moving averages
# --------------------------------------------------------------------------
def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window=period, min_periods=period).mean()


# --------------------------------------------------------------------------
# RSI (Wilder's smoothing, the industry-standard definition)
# --------------------------------------------------------------------------
def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index using Wilder's smoothing method."""
    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # Wilder's smoothing == an EMA with alpha = 1/period
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_values = 100 - (100 / (1 + rs))

    # Where avg_loss is 0 (pure uptrend), RSI is defined as 100.
    rsi_values = rsi_values.where(avg_loss != 0, 100.0)
    return rsi_values


# --------------------------------------------------------------------------
# MACD
# --------------------------------------------------------------------------
def macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Moving Average Convergence Divergence.

    Returns:
        Tuple of (macd_line, signal_line, histogram).
    """
    ema_fast = series.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = series.ewm(span=slow, adjust=False, min_periods=slow).mean()

    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram


# --------------------------------------------------------------------------
# ADX (Average Directional Index), Wilder's method
# --------------------------------------------------------------------------
def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Average Directional Index — measures trend strength (not direction).

    Expects ``df`` to contain ``High``, ``Low``, ``Close`` columns.
    """
    high, low, close = df["High"], df["Low"], df["Close"]

    prev_high = high.shift(1)
    prev_low = low.shift(1)
    prev_close = close.shift(1)

    up_move = high - prev_high
    down_move = prev_low - low

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    plus_dm_series = pd.Series(plus_dm, index=df.index)
    minus_dm_series = pd.Series(minus_dm, index=df.index)

    plus_di = 100 * (
        plus_dm_series.ewm(alpha=1 / period, min_periods=period, adjust=False).mean() / atr
    )
    minus_di = 100 * (
        minus_dm_series.ewm(alpha=1 / period, min_periods=period, adjust=False).mean() / atr
    )

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_values = dx.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    return adx_values


# --------------------------------------------------------------------------
# Volume / 52-week levels
# --------------------------------------------------------------------------
def avg_volume(volume: pd.Series, period: int = 20) -> pd.Series:
    """Rolling average volume."""
    return volume.rolling(window=period, min_periods=period).mean()


def fifty_two_week_high(close: pd.Series) -> pd.Series:
    """Rolling 52-week (252 trading day) high of the close price."""
    return close.rolling(window=252, min_periods=1).max()


def fifty_two_week_low(close: pd.Series) -> pd.Series:
    """Rolling 52-week (252 trading day) low of the close price."""
    return close.rolling(window=252, min_periods=1).min()


# --------------------------------------------------------------------------
# Orchestration: compute every indicator and return the enriched DataFrame
# --------------------------------------------------------------------------
def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute every indicator used by the scanner and append them as columns.

    This is the single entry point ``scanner.py`` calls per stock. Adding a
    new indicator later means adding one function above and one line here.

    Args:
        df: OHLCV DataFrame with columns [Open, High, Low, Close, Volume].

    Returns:
        A copy of ``df`` with additional indicator columns.
    """
    out = df.copy()
    close = out["Close"]

    out["EMA20"] = ema(close, 20)
    out["EMA50"] = ema(close, 50)
    out["EMA100"] = ema(close, 100)
    out["EMA200"] = ema(close, 200)

    out["RSI14"] = rsi(close, 14)

    macd_line, signal_line, hist = macd(close)
    out["MACD"] = macd_line
    out["MACD_Signal"] = signal_line
    out["MACD_Hist"] = hist

    out["ADX14"] = adx(out, 14)

    out["Vol_Avg20"] = avg_volume(out["Volume"], 20)

    out["High_52W"] = fifty_two_week_high(close)
    out["Low_52W"] = fifty_two_week_low(close)

    return out
