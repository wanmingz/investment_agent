"""Valuation metrics via yfinance .info (free, delayed)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ValuationMetrics:
    symbol: str
    label: str
    trailing_pe: float | None = None
    forward_pe: float | None = None
    price_to_book: float | None = None
    market_cap_b: float | None = None


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
        if f != f:  # NaN
            return None
        return f
    except (TypeError, ValueError):
        return None


def fetch_valuation_metrics(symbol: str, *, label: str = "") -> ValuationMetrics:
    label = label or symbol
    out = ValuationMetrics(symbol=symbol.upper(), label=label)
    try:
        import yfinance as yf
    except ImportError:
        return out

    try:
        info = yf.Ticker(symbol).info or {}
        out.trailing_pe = _safe_float(info.get("trailingPE"))
        out.forward_pe = _safe_float(info.get("forwardPE"))
        out.price_to_book = _safe_float(info.get("priceToBook"))
        cap = _safe_float(info.get("marketCap"))
        if cap is not None:
            out.market_cap_b = cap / 1e9
    except Exception:  # noqa: BLE001
        pass

    return out
