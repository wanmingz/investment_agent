"""Markets agent input — fetch + ``MarketsInput``."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from investment_agent.agents.markets.snapshot import (
    FundamentalsSnapshot,
    VolSnapshot,
    fetch_fundamentals_snapshot,
    fetch_vol_snapshot,
)
from investment_agent.config import Settings


@dataclass(frozen=True)
class MarketSnapshots:
    """Raw yfinance payloads for one run (Markets full blocks; Regime derives summary)."""

    fundamentals: FundamentalsSnapshot
    vol: VolSnapshot


@dataclass(frozen=True)
class MarketsInput:
    as_of: date
    region: str
    fundamentals: FundamentalsSnapshot
    vol: VolSnapshot


def fetch_market_snapshots(
    settings: Settings,
    *,
    as_of: date,
) -> tuple[MarketSnapshots, list[str]]:
    notes: list[str] = []
    fundamentals = fetch_fundamentals_snapshot(
        as_of=as_of,
        finnhub_key=settings.finnhub_api_key,
    )
    notes.append(f"fundamentals:{len(fundamentals.rows)} symbols")

    vol = fetch_vol_snapshot()
    if vol.notes:
        notes.append("vol:" + "; ".join(vol.notes[:3]))

    return MarketSnapshots(fundamentals=fundamentals, vol=vol), notes


def build_markets_input(
    snapshots: MarketSnapshots,
    *,
    as_of: date,
    region: str,
) -> MarketsInput:
    return MarketsInput(
        as_of=as_of,
        region=region,
        fundamentals=snapshots.fundamentals,
        vol=snapshots.vol,
    )
