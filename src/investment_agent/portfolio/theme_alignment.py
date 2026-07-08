"""Theme–portfolio alignment (read-only overlay)."""

from __future__ import annotations

from datetime import date

from investment_agent.models import FinalTheme, InvestmentBrief, theme_rank_score
from investment_agent.portfolio.models import (
    Position,
    PortfolioSnapshot,
    ThemeAlignmentReport,
    ThemeAlignmentRow,
    UncoveredPosition,
)
from investment_agent.universe.constants import SECTOR_ETFS
from investment_agent.universe.symbols import extract_tickers_from_themes, sector_key_for_symbol

_HIGH_OVERLAP_PCT = 25.0

# Sector label tokens in theme tickers_or_sectors text (lowercase)
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


def _position_weight(pos: Position, total_nav: float) -> float:
    if total_nav <= 0:
        return 0.0
    mkt = pos.market_value if pos.market_value is not None else pos.cost_basis
    return float(mkt) / total_nav * 100.0


def _theme_sector_keys(theme: FinalTheme) -> set[str]:
    sectors: set[str] = set()
    for ticker in extract_tickers_from_themes(theme.tickers_or_sectors):
        key = sector_key_for_symbol(ticker)
        if key:
            sectors.add(key)
    for raw in theme.tickers_or_sectors:
        for token in raw.lower().replace("/", " ").replace(",", " ").split():
            token = token.strip()
            if token in _SECTOR_LABEL_TOKENS:
                sectors.add(_SECTOR_LABEL_TOKENS[token])
            sym = token.upper().lstrip("$")
            if sym in SECTOR_ETFS.values():
                key = sector_key_for_symbol(sym)
                if key:
                    sectors.add(key)
    name_tokens = theme.name.lower().replace("-", " ").split()
    for token in name_tokens:
        if token in _SECTOR_LABEL_TOKENS:
            sectors.add(_SECTOR_LABEL_TOKENS[token])
    return sectors


def _theme_tickers(theme: FinalTheme) -> set[str]:
    return {t.upper() for t in extract_tickers_from_themes(theme.tickers_or_sectors)}


def _position_matches_theme(pos: Position, theme: FinalTheme) -> bool:
    sym = pos.symbol.upper()
    if sym in _theme_tickers(theme):
        return True
    sectors = _theme_sector_keys(theme)
    if not sectors:
        return False
    pos_sector = sector_key_for_symbol(sym)
    return pos_sector is not None and pos_sector in sectors


def compute_theme_alignment(
    brief: InvestmentBrief,
    snapshot: PortfolioSnapshot,
    *,
    top_n: int = 8,
) -> ThemeAlignmentReport:
    """Match top brief themes to open positions by ticker and sector."""
    total_nav = snapshot.total_nav if snapshot.total_nav > 0 else snapshot.total_market_value
    sorted_themes = sorted(brief.themes, key=theme_rank_score, reverse=True)[:top_n]

    rows: list[ThemeAlignmentRow] = []
    matched_symbols: set[str] = set()

    for rank, theme in enumerate(sorted_themes, start=1):
        overlap_symbols: list[str] = []
        overlap_value = 0.0
        for pos in snapshot.positions:
            if _position_matches_theme(pos, theme):
                overlap_symbols.append(pos.symbol)
                mkt = pos.market_value if pos.market_value is not None else pos.cost_basis
                overlap_value += float(mkt)
                matched_symbols.add(pos.symbol.upper())

        overlap_pct = (overlap_value / total_nav * 100.0) if total_nav > 0 else 0.0
        if overlap_pct >= _HIGH_OVERLAP_PCT:
            status = "high"
        elif overlap_pct > 0:
            status = "partial"
        else:
            status = "gap"

        rows.append(
            ThemeAlignmentRow(
                theme_name=theme.name,
                rank=rank,
                overlap_symbols=sorted(overlap_symbols),
                overlap_pct=overlap_pct,
                status=status,
                theme_tickers=sorted(_theme_tickers(theme)),
            )
        )

    uncovered: list[UncoveredPosition] = []
    for pos in snapshot.positions:
        if pos.symbol.upper() not in matched_symbols:
            uncovered.append(
                UncoveredPosition(
                    symbol=pos.symbol,
                    name=pos.name,
                    weight_pct=_position_weight(pos, total_nav),
                )
            )

    gap_themes = [r.theme_name for r in rows if r.status == "gap"]

    as_of = snapshot.as_of
    if brief.report_date:
        try:
            from datetime import date as date_cls

            as_of = date_cls.fromisoformat(brief.report_date)
        except ValueError:
            pass

    return ThemeAlignmentReport(
        as_of=as_of,
        rows=rows,
        uncovered_positions=uncovered,
        gap_themes=gap_themes,
        total_nav=total_nav,
    )
