"""Tests for benchmark-only model target allocation."""

from __future__ import annotations

from investment_agent.models import FinalTheme, InvestmentBrief, ThemeStage
from investment_agent.portfolio.model.allocation import compute_model_target_allocation
from investment_agent.universe.constants import BENCHMARK_SYMBOL, SECTOR_ETFS
from investment_agent.universe.symbols import is_benchmark_symbol


def _theme(name: str, tickers: list[str], score: float = 1.0) -> FinalTheme:
    half = score / 2
    return FinalTheme(
        name=name,
        thesis="t",
        stage=ThemeStage.MID,
        consensus_score=half,
        investability_score=half,
        synthesis="s",
        key_drivers=[],
        risks=[],
        tickers_or_sectors=tickers,
    )


def _brief(*themes: FinalTheme) -> InvestmentBrief:
    return InvestmentBrief(
        report_date="2026-07-01",
        as_of_context="As of 2026-07-01",
        executive_summary="x",
        regime_view="r",
        themes=list(themes),
    )


def test_model_maps_tech_theme_to_xlk_not_single_stocks() -> None:
    brief = _brief(_theme("Tech momentum", ["AAPL", "NVDA"], score=1.0))
    target = compute_model_target_allocation(brief)
    assert [r.symbol for r in target.rows] == [SECTOR_ETFS["Tech"]]
    assert target.rows[0].target_pct == 100.0
    assert all(is_benchmark_symbol(r.symbol) for r in target.rows)


def test_model_ignores_single_stock_tickers_in_weighting() -> None:
    brief = _brief(
        _theme("A", ["AAPL"], score=1.6),
        _theme("B", ["MSFT"], score=0.8),
    )
    target = compute_model_target_allocation(brief)
    symbols = {r.symbol for r in target.rows}
    assert "AAPL" not in symbols
    assert "MSFT" not in symbols
    assert symbols == {BENCHMARK_SYMBOL}


def test_model_merges_same_sector_etf() -> None:
    brief = _brief(
        _theme("Tech A", ["AAPL"], score=1.0),
        _theme("Tech B", ["NVDA"], score=1.0),
    )
    target = compute_model_target_allocation(brief)
    assert len(target.rows) == 1
    assert target.rows[0].symbol == SECTOR_ETFS["Tech"]
    assert target.rows[0].target_pct == 100.0


def test_model_energy_theme_uses_sector_etf() -> None:
    brief = _brief(_theme("Energy rally", ["XOM", "CVX"], score=1.0))
    target = compute_model_target_allocation(brief)
    assert target.rows[0].symbol == SECTOR_ETFS["Energy"]
