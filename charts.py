"""
charts.py
---------
Plotly chart builders used by the Streamlit detail page: a candlestick
chart with EMA overlays, plus Volume, RSI, and MACD sub-panels.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from utils import get_logger

logger = get_logger(__name__)

_EMA_COLORS = {
    "EMA20": "#2962FF",
    "EMA50": "#FF6D00",
    "EMA100": "#AA00FF",
    "EMA200": "#000000",
}


def build_detail_chart(df: pd.DataFrame, symbol: str, lookback_days: int = 300) -> go.Figure:
    """
    Build a multi-panel chart: candlesticks + EMAs on top, Volume, RSI, and
    MACD below — sharing a synchronized x-axis (time range slider zooms all
    panels together).

    Args:
        df: Enriched OHLCV+indicator DataFrame (output of
            ``indicators.compute_all_indicators``).
        symbol: Ticker symbol, used in the chart title.
        lookback_days: Number of most-recent trading days to display.

    Returns:
        A Plotly Figure ready to render with ``st.plotly_chart``.
    """
    plot_df = df.tail(lookback_days).copy()

    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.5, 0.15, 0.15, 0.2],
        subplot_titles=("Price & EMAs", "Volume", "RSI (14)", "MACD"),
    )

    # --- Row 1: Candlesticks + EMAs -----------------------------------
    fig.add_trace(
        go.Candlestick(
            x=plot_df.index,
            open=plot_df["Open"],
            high=plot_df["High"],
            low=plot_df["Low"],
            close=plot_df["Close"],
            name="Price",
            increasing_line_color="#26A69A",
            decreasing_line_color="#EF5350",
        ),
        row=1,
        col=1,
    )

    for ema_col, color in _EMA_COLORS.items():
        if ema_col in plot_df.columns:
            fig.add_trace(
                go.Scatter(
                    x=plot_df.index,
                    y=plot_df[ema_col],
                    mode="lines",
                    name=ema_col,
                    line=dict(color=color, width=1.3),
                ),
                row=1,
                col=1,
            )

    # --- Row 2: Volume ---------------------------------------------------
    volume_colors = [
        "#26A69A" if c >= o else "#EF5350"
        for c, o in zip(plot_df["Close"], plot_df["Open"])
    ]
    fig.add_trace(
        go.Bar(x=plot_df.index, y=plot_df["Volume"], name="Volume", marker_color=volume_colors),
        row=2,
        col=1,
    )

    # --- Row 3: RSI --------------------------------------------------------
    if "RSI14" in plot_df.columns:
        fig.add_trace(
            go.Scatter(x=plot_df.index, y=plot_df["RSI14"], mode="lines", name="RSI(14)", line=dict(color="#7B1FA2")),
            row=3,
            col=1,
        )
        fig.add_hline(y=70, line_dash="dot", line_color="red", row=3, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="green", row=3, col=1)

    # --- Row 4: MACD --------------------------------------------------
    if {"MACD", "MACD_Signal", "MACD_Hist"}.issubset(plot_df.columns):
        fig.add_trace(
            go.Scatter(x=plot_df.index, y=plot_df["MACD"], mode="lines", name="MACD", line=dict(color="#1E88E5")),
            row=4,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=plot_df.index,
                y=plot_df["MACD_Signal"],
                mode="lines",
                name="Signal",
                line=dict(color="#FB8C00"),
            ),
            row=4,
            col=1,
        )
        hist_colors = ["#26A69A" if v >= 0 else "#EF5350" for v in plot_df["MACD_Hist"]]
        fig.add_trace(
            go.Bar(x=plot_df.index, y=plot_df["MACD_Hist"], name="Histogram", marker_color=hist_colors),
            row=4,
            col=1,
        )

    fig.update_layout(
        title=f"{symbol} — Price, Volume & Indicators",
        height=900,
        showlegend=True,
        xaxis_rangeslider_visible=False,
        template="plotly_white",
        margin=dict(l=40, r=40, t=60, b=20),
    )

    return fig
