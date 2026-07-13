"""Actual vs target portfolio weights."""

from __future__ import annotations

from investment_agent.models import InvestmentBrief, theme_rank_score
from investment_agent.portfolio.manual.theme_alignment import (
    _position_matches_theme,
    _position_weight,
)
from investment_agent.portfolio.models import (
    DriftReport,
    DriftRow,
    PortfolioSnapshot,
    TargetAllocation,
)
from investment_agent.universe.symbols import benchmark_etf_for_theme, is_benchmark_symbol


def _actual_weight_pct(snapshot: PortfolioSnapshot, symbol: str) -> float:
    total_nav = snapshot.total_nav if snapshot.total_nav > 0 else snapshot.total_market_value
    if total_nav <= 0:
        return 0.0
    upper = symbol.upper()
    for pos in snapshot.positions:
        if pos.symbol.upper() != upper:
            continue
        mkt = pos.market_value if pos.market_value is not None else pos.cost_basis
        return float(mkt) / total_nav * 100.0
    return 0.0


def _severity(drift_pp: float, band_pp: float) -> str:
    ad = abs(drift_pp)
    if ad < band_pp:
        return "ok"
    if ad < band_pp * 2:
        return "watch"
    return "alert"


def compute_drift_report(
    snapshot: PortfolioSnapshot,
    target: TargetAllocation,
    *,
    band_pp: float = 5.0,
) -> DriftReport:
    """Compare mark-to-market weights to target allocation."""
    target_map = {r.symbol.upper(): r.target_pct for r in target.rows}
    symbols = sorted(set(target_map) | {p.symbol.upper() for p in snapshot.positions})

    total_nav = snapshot.total_nav if snapshot.total_nav > 0 else snapshot.total_market_value
    rows: list[DriftRow] = []
    for sym in symbols:
        target_pct = target_map.get(sym, 0.0)
        actual_pct = _actual_weight_pct(snapshot, sym)
        drift_pp = actual_pct - target_pct
        rows.append(
            DriftRow(
                symbol=sym,
                target_pct=target_pct,
                actual_pct=actual_pct,
                drift_pp=drift_pp,
                severity=_severity(drift_pp, band_pp),
            )
        )

    rows.sort(key=lambda r: abs(r.drift_pp), reverse=True)
    return DriftReport(
        as_of=snapshot.as_of,
        band_pp=band_pp,
        rows=rows,
        total_nav=total_nav,
    )


def _benchmark_bucket_for_position(
    brief: InvestmentBrief,
    pos,
    *,
    top_n: int,
) -> str | None:
    """Map a holding to one sector ETF / SPY via brief theme overlap."""
    sym = pos.symbol.upper()
    if is_benchmark_symbol(sym):
        return sym
    themes = sorted(brief.themes, key=theme_rank_score, reverse=True)[:top_n]
    for theme in themes:
        if _position_matches_theme(pos, theme):
            return benchmark_etf_for_theme(theme.name, theme.tickers_or_sectors)
    return None


def _benchmark_actual_weights(
    brief: InvestmentBrief,
    snapshot: PortfolioSnapshot,
    target: TargetAllocation,
    *,
    top_n: int,
) -> tuple[dict[str, float], float]:
    """Roll manual holdings into benchmark ETF weights; return (actual map, uncovered %)."""
    total_nav = snapshot.total_nav if snapshot.total_nav > 0 else snapshot.total_market_value
    actual: dict[str, float] = {r.symbol.upper(): 0.0 for r in target.rows}
    uncovered_pct = 0.0
    for pos in snapshot.positions:
        weight = _position_weight(pos, total_nav)
        bucket = _benchmark_bucket_for_position(brief, pos, top_n=top_n)
        if bucket is None:
            uncovered_pct += weight
            continue
        key = bucket.upper()
        actual[key] = actual.get(key, 0.0) + weight
    return actual, uncovered_pct


def compute_benchmark_drift_report(
    brief: InvestmentBrief,
    snapshot: PortfolioSnapshot,
    target: TargetAllocation,
    *,
    top_n: int = 8,
    band_pp: float = 5.0,
) -> tuple[DriftReport, float]:
    """
    Compare manual holdings vs benchmark targets (sector ETFs / SPY).

    Single-stock positions roll up to the ETF of their highest-ranked matching theme.
    Returns ``(report, uncovered_pct)`` for holdings that match no brief theme.
    """
    target_map = {r.symbol.upper(): r.target_pct for r in target.rows}
    actual_map, uncovered_pct = _benchmark_actual_weights(
        brief, snapshot, target, top_n=top_n
    )

    total_nav = snapshot.total_nav if snapshot.total_nav > 0 else snapshot.total_market_value
    rows: list[DriftRow] = []
    for sym in sorted(target_map):
        target_pct = target_map[sym]
        actual_pct = actual_map.get(sym, 0.0)
        drift_pp = actual_pct - target_pct
        rows.append(
            DriftRow(
                symbol=sym,
                target_pct=target_pct,
                actual_pct=actual_pct,
                drift_pp=drift_pp,
                severity=_severity(drift_pp, band_pp),
            )
        )

    rows.sort(key=lambda r: abs(r.drift_pp), reverse=True)
    report = DriftReport(
        as_of=snapshot.as_of,
        band_pp=band_pp,
        rows=rows,
        total_nav=total_nav,
    )
    return report, uncovered_pct
