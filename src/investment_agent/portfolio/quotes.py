"""yfinance quote helpers for portfolio trade entry and mark-to-market."""

from __future__ import annotations

from datetime import date, timedelta


def fetch_close_on_date(symbol: str, on_date: date) -> float | None:
    """Closing price for *symbol* on *on_date* (or last session on/before that date)."""
    sym = symbol.strip().upper()
    if not sym:
        return None
    try:
        import yfinance as yf
    except ImportError:
        return None

    try:
        end = on_date + timedelta(days=1)
        start = on_date - timedelta(days=10)
        hist = yf.Ticker(sym).history(
            start=start.isoformat(),
            end=end.isoformat(),
            auto_adjust=True,
        )
        if hist.empty or "Close" not in hist.columns:
            return None
        close = hist["Close"].dropna()
        if close.empty:
            return None
        on_or_before = close[[ts.date() <= on_date for ts in close.index]]
        if on_or_before.empty:
            return None
        return float(on_or_before.iloc[-1])
    except Exception:  # noqa: BLE001 — best-effort
        return None


def fetch_symbol_name(symbol: str) -> str:
    """Company/security display name from yfinance (shortName or longName)."""
    sym = symbol.strip().upper()
    if not sym:
        return ""
    try:
        import yfinance as yf
    except ImportError:
        return ""

    try:
        info = yf.Ticker(sym).info or {}
        return str(info.get("shortName") or info.get("longName") or "").strip()
    except Exception:  # noqa: BLE001 — best-effort
        return ""
