"""Data Plane orchestrator — one input builder per agent package.

  agents/regime/input.py    → RegimeInput
  agents/narrative/input.py → NarrativeInput
  agents/markets/input.py   → MarketsInput (+ shared yfinance fetch)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from investment_agent.agents.markets.input import (
    MarketsInput,
    build_markets_input,
    fetch_market_snapshots,
)
from investment_agent.agents.narrative.input import NarrativeInput, build_narrative_input
from investment_agent.agents.regime.input import RegimeInput, build_regime_input
from investment_agent.config import Settings

# Re-exports for checkpoint and external callers
__all__ = [
    "RegimeInput",
    "NarrativeInput",
    "MarketsInput",
    "DataPlaneSnapshot",
    "build_data_plane",
]


@dataclass
class DataPlaneSnapshot:
    as_of: date
    region: str
    regime_input: RegimeInput
    narrative_input: NarrativeInput
    markets_input: MarketsInput
    data_plane_notes: list[str] = field(default_factory=list)


def build_data_plane(
    settings: Settings,
    *,
    as_of: date | None = None,
) -> DataPlaneSnapshot:
    as_of = as_of or date.today()
    region = settings.market_region
    notes: list[str] = []

    market_snapshots, market_notes = fetch_market_snapshots(settings, as_of=as_of)
    notes.extend(market_notes)

    regime_input, regime_notes = build_regime_input(
        market_snapshots, as_of=as_of, region=region
    )
    notes.extend(regime_notes)

    narrative_input, narrative_notes = build_narrative_input(
        settings, as_of=as_of, region=region
    )
    notes.extend(narrative_notes)

    markets_input = build_markets_input(
        market_snapshots, as_of=as_of, region=region
    )

    return DataPlaneSnapshot(
        as_of=as_of,
        region=region,
        regime_input=regime_input,
        narrative_input=narrative_input,
        markets_input=markets_input,
        data_plane_notes=notes,
    )
