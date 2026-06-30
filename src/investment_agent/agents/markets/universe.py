"""Sector ETF + benchmark universe for Markets agent yfinance fetches.

Regime agent reads a derived summary built from the same snapshots (see ``agents/regime/input.py``).
"""

from __future__ import annotations

import re

# Sector proxies for yfinance fetches (Markets + Regime summary)
SECTOR_ETFS: dict[str, str] = {
    "Tech": "XLK",
    "Energy": "XLE",
    "Healthcare": "XLV",
    "Financials": "XLF",
    "AI/Cloud": "IGV",
    "Consumer": "XLY",
    "Industrials": "XLI",
    "Utilities": "XLU",
}

BENCHMARK_SYMBOL = "SPY"

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def is_likely_ticker(token: str) -> bool:
    t = token.strip().upper().replace("$", "")
    if not t or len(t) > 10:
        return False
    if t in SECTOR_ETFS.values() or t == BENCHMARK_SYMBOL:
        return True
    return bool(_TICKER_RE.match(t))


def extract_tickers_from_themes(tickers_or_sectors: list[str]) -> list[str]:
    """Pull explicit tickers from theme fields (skip plain sector names)."""
    found: list[str] = []
    for raw in tickers_or_sectors:
        for part in re.split(r"[,;/\s]+", raw.strip()):
            part = part.strip().upper().lstrip("$")
            if is_likely_ticker(part):
                found.append(part)
    return found


def symbols_for_fundamentals(
    theme_tickers: list[str],
    *,
    max_extra: int = 8,
) -> tuple[list[tuple[str, str]], list[str]]:
    """
    Returns (labeled_symbols, notes).
    labeled_symbols: (label, symbol) — sectors first, then theme tickers, SPY benchmark.
    """
    notes: list[str] = []
    labeled: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(label: str, symbol: str) -> None:
        sym = symbol.upper()
        if sym in seen:
            return
        seen.add(sym)
        labeled.append((label, sym))

    for label, sym in SECTOR_ETFS.items():
        add(label, sym)
    add("Benchmark", BENCHMARK_SYMBOL)

    extra = 0
    for sym in theme_tickers:
        if extra >= max_extra:
            notes.append(f"Theme tickers capped at {max_extra} extra symbols")
            break
        if sym.upper() not in seen:
            add(f"Theme:{sym}", sym.upper())
            extra += 1

    return labeled, notes
