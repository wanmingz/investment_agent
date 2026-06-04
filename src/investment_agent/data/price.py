"""Price and momentum metrics via yfinance (free)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PriceMetrics:
    symbol: str
    label: str
    last_close: float | None = None
    return_20d_pct: float | None = None
    return_60d_pct: float | None = None
    pct_from_52w_high: float | None = None
    vs_spy_20d_pct: float | None = None


def _return_pct(close, days: int) -> float | None:
    if close is None or len(close) < days + 1:
        return None
    try:
        start = float(close.iloc[-(days + 1)])
        end = float(close.iloc[-1])
        if start == 0:
            return None
        return (end / start - 1) * 100
    except (IndexError, TypeError, ValueError):
        return None


def fetch_price_metrics(
    symbol: str,
    *,
    label: str = "",
    spy_return_20d: float | None = None,
) -> PriceMetrics:
    label = label or symbol
    out = PriceMetrics(symbol=symbol.upper(), label=label)
    try:
        import yfinance as yf
    except ImportError:
        return out

    try:
        hist = yf.Ticker(symbol).history(period="1y")
        if hist.empty or "Close" not in hist.columns:
            return out
        close = hist["Close"].dropna()
        if close.empty:
            return out

        out.last_close = float(close.iloc[-1])
        out.return_20d_pct = _return_pct(close, 20)
        out.return_60d_pct = _return_pct(close, 60)

        high_52w = float(close.max())
        if high_52w > 0:
            out.pct_from_52w_high = (out.last_close / high_52w - 1) * 100

        if spy_return_20d is not None and out.return_20d_pct is not None:
            out.vs_spy_20d_pct = out.return_20d_pct - spy_return_20d
    except Exception:  # noqa: BLE001 — best-effort
        pass

    return out
