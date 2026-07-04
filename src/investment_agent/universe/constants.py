"""Shared sector ETF registry — single source for fetch, regime, and brief clustering."""

from __future__ import annotations

SECTOR_ETFS: dict[str, str] = {
    "Tech": "XLK",
    "Energy": "XLE",
    "Healthcare": "XLV",
    "Financials": "XLF",
    "AI": "AIQ",
    "Cloud": "SKYY",
    "Consumer": "XLY",
    "Industrials": "XLI",
    "Utilities": "XLU",
}

BENCHMARK_SYMBOL = "SPY"
VIX_SYMBOL = "^VIX"

VOL_SECTOR_LABELS = frozenset(
    {"Tech", "Energy", "Healthcare", "Financials", "AI", "Cloud"}
)

# Human label → canonical sector key (brief assembler clustering)
_LABEL_SECTOR_KEY: dict[str, str] = {
    "Tech": "tech",
    "Energy": "energy",
    "Healthcare": "healthcare",
    "Financials": "financials",
    "AI": "ai",
    "Cloud": "cloud",
    "Consumer": "consumer",
    "Industrials": "industrials",
    "Utilities": "utilities",
}

assert set(_LABEL_SECTOR_KEY) == set(SECTOR_ETFS)

SECTOR_DISPLAY_ETF: dict[str, str] = {
    "tech": "Tech",
    "energy": "Energy",
    "financials": "Financials",
    "healthcare": "Healthcare",
    "ai": "AI",
    "cloud": "Cloud",
    "consumer": "Consumer",
    "industrials": "Industrials",
    "utilities": "Utilities",
}


def build_ticker_to_sector(
    sector_etfs: dict[str, str] | None = None,
    benchmark: str = BENCHMARK_SYMBOL,
) -> dict[str, str]:
    etfs = sector_etfs if sector_etfs is not None else SECTOR_ETFS
    out: dict[str, str] = {}
    for label, sym in etfs.items():
        key = _LABEL_SECTOR_KEY.get(label)
        if key is None:
            key = label.lower().replace("/", "_").replace(" ", "_")
        out[sym.lower()] = key
    out[benchmark.lower()] = "benchmark"
    return out


TICKER_TO_SECTOR: dict[str, str] = build_ticker_to_sector()
