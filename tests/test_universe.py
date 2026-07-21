"""Tests for shared market universe registry."""

from investment_agent.universe import (
    BENCHMARK_SYMBOL,
    SECTOR_ETFS,
    SECTOR_ETFS_ALT,
    TICKER_TO_SECTOR,
    VIX_SYMBOL,
    build_ticker_to_sector,
    display_tickers_for_theme,
    symbols_for_fundamentals,
    vol_labeled_symbols,
)


def test_ticker_to_sector_maps_all_sector_etfs():
    expected = {
        "xlk": "tech",
        "xle": "energy",
        "xlv": "healthcare",
        "xlf": "financials",
        "aiq": "ai",
        "skyy": "cloud",
        "xly": "consumer",
        "xli": "industrials",
        "xlu": "utilities",
        "spy": "benchmark",
    }
    for sym, sector in expected.items():
        assert TICKER_TO_SECTOR[sym] == sector


def test_symbols_for_fundamentals_core_ten():
    labeled, notes = symbols_for_fundamentals([], max_extra=0)
    assert len(labeled) == 10
    assert notes == []
    symbols = {sym for _, sym in labeled}
    assert symbols == set(SECTOR_ETFS.values()) | {BENCHMARK_SYMBOL}


def test_vol_labeled_symbols_seven_pairs():
    pairs = vol_labeled_symbols()
    assert len(pairs) == 7
    assert pairs[0] == ("VIX", VIX_SYMBOL)
    vol_symbols = {sym for _, sym in pairs[1:]}
    assert vol_symbols <= set(SECTOR_ETFS.values())
    assert vol_symbols == {"XLK", "XLE", "XLV", "XLF", "AIQ", "SKYY"}


def test_custom_sector_etfs_propagates_to_helpers():
    custom = {"Tech": "XLK", "Energy": "XLE"}
    labeled, _ = symbols_for_fundamentals([], max_extra=0, sector_etfs=custom)
    assert len(labeled) == 3  # 2 sectors + SPY
    assert build_ticker_to_sector(custom) == {"xlk": "tech", "xle": "energy", "spy": "benchmark"}


def test_sector_etfs_alt_covers_same_labels():
    assert set(SECTOR_ETFS_ALT) == set(SECTOR_ETFS)
    assert set(SECTOR_ETFS_ALT.values()).isdisjoint(SECTOR_ETFS.values())


def test_display_tickers_appends_primary_and_alt_etfs():
    shown = display_tickers_for_theme("AI Infrastructure buildout", ["NVDA", "AIQ"])
    assert shown[:2] == [SECTOR_ETFS["AI"], SECTOR_ETFS_ALT["AI"]]
    assert "NVDA" in shown


def test_display_tickers_from_sector_name_alone():
    shown = display_tickers_for_theme("Tech momentum", [])
    assert shown == [SECTOR_ETFS["Tech"], SECTOR_ETFS_ALT["Tech"]]


def test_display_tickers_sector_label_theme():
    shown = display_tickers_for_theme("Energy", ["XLE", "Energy ETFs"])
    assert shown[:2] == ["XLE", "XOP"]
