"""Regime agent input — cross-asset summary derived from market snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from investment_agent.agents.markets.input import MarketSnapshots
from investment_agent.agents.markets.snapshot import FundamentalsSnapshot, VolSnapshot
from investment_agent.agents.markets.universe import BENCHMARK_SYMBOL


@dataclass(frozen=True)
class RegimeInput:
    as_of: date
    region: str
    regime_context_block: str = ""
    context_notes: tuple[str, ...] = ()


def _build_regime_context_block(
    *,
    fundamentals: FundamentalsSnapshot,
    vol: VolSnapshot,
    as_of: date,
    region: str,
) -> tuple[str, list[str]]:
    notes: list[str] = []
    lines = [
        "## Cross-asset regime context (yfinance — regime lens only)",
        f"As-of: {as_of.isoformat()}",
        f"Region focus: {region}",
        "Use ONLY these figures for quantitative claims in regime_backdrop and themes.",
    ]

    lines.append("\n### Volatility / risk")
    if vol.vix_level is not None:
        lines.append(f"- VIX proxy (^VIX): {vol.vix_level:.2f}")
    else:
        lines.append("- VIX proxy: unavailable")
        notes.append("regime:vix unavailable")
    if vol.vix_20d_change_pct is not None:
        lines.append(f"- VIX 20d change: {vol.vix_20d_change_pct:+.1f}%")
    if vol.sector_vol:
        for label, ann in sorted(vol.sector_vol.items()):
            lines.append(f"- {label} 20d ann. vol: {ann:.1%}")
    if vol.notes:
        lines.append("- Vol fetch notes: " + "; ".join(vol.notes[:4]))

    lines.append("\n### Sector rotation vs benchmark (ETF snapshot)")
    spy = next((r for r in fundamentals.rows if r.symbol == BENCHMARK_SYMBOL), None)
    if spy and spy.price.return_20d_pct is not None:
        lines.append(f"- {BENCHMARK_SYMBOL} 20d return: {spy.price.return_20d_pct:+.1f}%")
    for row in fundamentals.rows:
        if row.symbol == BENCHMARK_SYMBOL:
            continue
        p = row.price
        parts = [f"- {row.label} ({row.symbol})"]
        if p.return_20d_pct is not None:
            parts.append(f"20d={p.return_20d_pct:+.1f}%")
        if p.vs_spy_20d_pct is not None:
            parts.append(f"vs_SPY={p.vs_spy_20d_pct:+.1f}pp")
        if len(parts) > 1:
            lines.append(" ".join(parts))

    if fundamentals.signals:
        lines.append("\n### Rule-based cross-asset hints")
        for s in fundamentals.signals[:8]:
            lines.append(f"- {s}")

    if fundamentals.notes:
        lines.append("\n### Fundamentals data notes")
        for n in fundamentals.notes[:3]:
            lines.append(f"- {n}")

    if not vol.vix_level and not fundamentals.rows:
        notes.append("regime:degraded context (no vol or ETF rows)")
        lines.append("\n(No live market data — use qualitative macro judgment only.)")

    return "\n".join(lines), notes


def build_regime_input(
    snapshots: MarketSnapshots,
    *,
    as_of: date,
    region: str,
) -> tuple[RegimeInput, list[str]]:
    block, notes = _build_regime_context_block(
        fundamentals=snapshots.fundamentals,
        vol=snapshots.vol,
        as_of=as_of,
        region=region,
    )
    return (
        RegimeInput(
            as_of=as_of,
            region=region,
            regime_context_block=block,
            context_notes=tuple(notes),
        ),
        notes,
    )
