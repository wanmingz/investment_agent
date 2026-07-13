"""Target ticker weights from theme brief (score-proportional)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from investment_agent.dates import analysis_date
from investment_agent.models import FinalTheme, InvestmentBrief, theme_rank_score
from investment_agent.portfolio.models import TargetAllocation, TargetWeightRow
from investment_agent.universe.symbols import (
    benchmark_etf_for_theme,
    extract_tickers_from_themes,
    is_benchmark_symbol,
)

InstrumentMode = Literal["tickers", "benchmark"]


def _allocation_as_of(brief: InvestmentBrief) -> date:
    if brief.report_date:
        try:
            return date.fromisoformat(brief.report_date)
        except ValueError:
            pass
    return analysis_date()


def _theme_symbols(theme: FinalTheme, instrument_mode: InstrumentMode) -> list[str]:
    if instrument_mode == "benchmark":
        return [benchmark_etf_for_theme(theme.name, theme.tickers_or_sectors)]
    return extract_tickers_from_themes(theme.tickers_or_sectors)


def compute_target_allocation(
    brief: InvestmentBrief,
    *,
    top_n: int = 8,
    investable_pct: float = 100.0,
    instrument_mode: InstrumentMode = "tickers",
) -> TargetAllocation:
    """
    Derive target weights from top brief themes.

    Theme weight is proportional to ``theme_rank_score`` (investability + consensus).

    * ``tickers`` — equal split across explicit tickers in ``tickers_or_sectors``.
    * ``benchmark`` — one sector ETF (or SPY) per theme; never single stocks.
    """
    themes = sorted(brief.themes, key=theme_rank_score, reverse=True)[:top_n]
    scored: list[tuple[str, float, list[str]]] = []
    score_total = 0.0

    for theme in themes:
        symbols = _theme_symbols(theme, instrument_mode)
        if not symbols:
            continue
        score = theme_rank_score(theme)
        if score <= 0:
            continue
        scored.append((theme.name, score, symbols))
        score_total += score

    raw_by_symbol: dict[str, tuple[float, list[str]]] = {}
    if score_total > 0:
        for theme_name, score, tickers in scored:
            theme_pct = score / score_total * investable_pct
            per_ticker = theme_pct / len(tickers)
            for sym in tickers:
                upper = sym.upper()
                if instrument_mode == "benchmark" and not is_benchmark_symbol(upper):
                    continue
                prev_pct, sources = raw_by_symbol.get(upper, (0.0, []))
                sources = list(sources)
                if theme_name not in sources:
                    sources.append(theme_name)
                raw_by_symbol[upper] = (prev_pct + per_ticker, sources)

    total_raw = sum(pct for pct, _ in raw_by_symbol.values())
    rows: list[TargetWeightRow] = []
    if total_raw > 0:
        scale = investable_pct / total_raw if total_raw > investable_pct + 1e-9 else 1.0
        for sym in sorted(raw_by_symbol):
            pct, sources = raw_by_symbol[sym]
            rows.append(
                TargetWeightRow(
                    symbol=sym,
                    target_pct=pct * scale,
                    source_themes=sources,
                )
            )

    total_target = sum(r.target_pct for r in rows)
    return TargetAllocation(
        as_of=_allocation_as_of(brief),
        top_n=top_n,
        rows=rows,
        total_target_pct=total_target,
    )
