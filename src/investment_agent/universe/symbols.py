"""Symbol list helpers derived from the shared universe registry."""

from __future__ import annotations

import re

from investment_agent.universe.constants import (
    BENCHMARK_SYMBOL,
    SECTOR_DISPLAY_ETF,
    SECTOR_ETFS,
    SECTOR_ETFS_ALT,
    TICKER_TO_SECTOR,
    VIX_SYMBOL,
    VOL_SECTOR_LABELS,
)

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")

_SECTOR_LABEL_TOKENS: dict[str, str] = {
    label.lower(): key
    for label, key in (
        ("tech", "tech"),
        ("technology", "tech"),
        ("energy", "energy"),
        ("healthcare", "healthcare"),
        ("health", "healthcare"),
        ("financials", "financials"),
        ("financial", "financials"),
        ("banks", "financials"),
        ("ai", "ai"),
        ("cloud", "cloud"),
        ("consumer", "consumer"),
        ("industrials", "industrials"),
        ("utilities", "utilities"),
    )
}

_SECTOR_PRIORITY = (
    "financials",
    "energy",
    "healthcare",
    "consumer",
    "industrials",
    "utilities",
    "ai",
    "cloud",
    "tech",
)


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


_ALT_ETF_TO_SECTOR: dict[str, str] = {
    SECTOR_ETFS_ALT[label].upper(): key
    for key, label in SECTOR_DISPLAY_ETF.items()
    if label in SECTOR_ETFS_ALT
}


def primary_sector_key(name: str, tickers_or_sectors: list[str]) -> str | None:
    """Canonical sector for a theme (title and sector labels/ETFs only — not single stocks)."""
    name_tags: set[str] = set()
    for token in name.lower().replace("-", " ").split():
        if token in _SECTOR_LABEL_TOKENS:
            name_tags.add(_SECTOR_LABEL_TOKENS[token])
    for sector in _SECTOR_PRIORITY:
        if sector in name_tags:
            return sector

    for raw in tickers_or_sectors:
        for part in re.split(r"[,;/\s]+", str(raw).strip()):
            token = part.strip().lower()
            if token in _SECTOR_LABEL_TOKENS:
                return _SECTOR_LABEL_TOKENS[token]
            sym = part.strip().upper().lstrip("$")
            if not sym:
                continue
            key = sector_key_for_symbol(sym)
            if key and key != "benchmark":
                return key
            alt_key = _ALT_ETF_TO_SECTOR.get(sym)
            if alt_key:
                return alt_key
    return None


def benchmark_etf_for_theme(name: str, tickers_or_sectors: list[str]) -> str:
    """Sector ETF from theme metadata, or SPY when sector is unknown."""
    key = primary_sector_key(name, tickers_or_sectors)
    if key:
        label = SECTOR_DISPLAY_ETF.get(key)
        if label and label in SECTOR_ETFS:
            return SECTOR_ETFS[label]
    return BENCHMARK_SYMBOL


def is_benchmark_symbol(symbol: str) -> bool:
    sym = symbol.strip().upper()
    return sym == BENCHMARK_SYMBOL or sym in SECTOR_ETFS.values()


def symbols_for_fundamentals(
    theme_tickers: list[str],
    *,
    max_extra: int = 8,
    sector_etfs: dict[str, str] | None = None,
) -> tuple[list[tuple[str, str]], list[str]]:
    """
    Returns (labeled_symbols, notes).
    labeled_symbols: (label, symbol) — sectors first, then theme tickers, SPY benchmark.
    """
    etfs = sector_etfs if sector_etfs is not None else SECTOR_ETFS
    notes: list[str] = []
    labeled: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(label: str, symbol: str) -> None:
        sym = symbol.upper()
        if sym in seen:
            return
        seen.add(sym)
        labeled.append((label, sym))

    for label, sym in etfs.items():
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


def vol_labeled_symbols(
    *,
    sector_etfs: dict[str, str] | None = None,
    vol_labels: frozenset[str] | None = None,
) -> list[tuple[str, str]]:
    etfs = sector_etfs if sector_etfs is not None else SECTOR_ETFS
    labels = vol_labels if vol_labels is not None else VOL_SECTOR_LABELS
    out: list[tuple[str, str]] = [("VIX", VIX_SYMBOL)]
    for label, sym in etfs.items():
        if label in labels:
            out.append((label, sym))
    return out


def sector_key_for_symbol(symbol: str) -> str | None:
    return TICKER_TO_SECTOR.get(symbol.strip().lower())


def universe_etfs_for_theme(name: str, tickers_or_sectors: list[str]) -> list[str]:
    """Primary + alt sector ETFs for a theme (dashboard display only)."""
    sector = primary_sector_key(name, tickers_or_sectors)
    if not sector:
        return []
    label = SECTOR_DISPLAY_ETF.get(sector)
    if not label:
        return []
    out: list[str] = []
    for sym in (SECTOR_ETFS.get(label), SECTOR_ETFS_ALT.get(label)):
        if sym:
            out.append(sym)
    return out


def display_tickers_for_theme(name: str, tickers_or_sectors: list[str]) -> list[str]:
    """Universe ETFs first, then remaining brief tickers — dashboard display only."""
    out: list[str] = []
    seen: set[str] = set()

    def add(item: str) -> None:
        raw = item.strip()
        if not raw:
            return
        key = raw.upper().lstrip("$")
        if key in seen:
            return
        seen.add(key)
        out.append(raw)

    for sym in universe_etfs_for_theme(name, tickers_or_sectors):
        add(sym)
    for item in tickers_or_sectors:
        add(item)
    return out
