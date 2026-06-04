"""Earnings revision proxy via Finnhub recommendation trends (free tier, optional)."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

FINNHUB_RECOMMENDATION = "https://finnhub.io/api/v1/stock/recommendation"


@dataclass
class RevisionMetrics:
    symbol: str
    label: str
    revision_proxy: float | None = None
    trend_label: str = ""
    strong_buy: int | None = None
    buy: int | None = None
    hold: int | None = None
    sell: int | None = None
    strong_sell: int | None = None


def _net_score(row: dict) -> float | None:
    try:
        sb = int(row.get("strongBuy") or 0)
        b = int(row.get("buy") or 0)
        h = int(row.get("hold") or 0)
        s = int(row.get("sell") or 0)
        ss = int(row.get("strongSell") or 0)
        total = sb + b + h + s + ss
        if total == 0:
            return None
        return (sb + b - s - ss) / total
    except (TypeError, ValueError):
        return None


def fetch_revision_metrics(
    symbol: str,
    *,
    label: str = "",
    finnhub_key: str = "",
) -> RevisionMetrics:
    label = label or symbol
    out = RevisionMetrics(symbol=symbol.upper(), label=label)
    if not finnhub_key:
        out.trend_label = "no Finnhub key"
        return out

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                FINNHUB_RECOMMENDATION,
                params={"symbol": symbol.upper(), "token": finnhub_key},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:  # noqa: BLE001
        out.trend_label = "fetch failed"
        return out

    if not isinstance(data, list) or not data:
        out.trend_label = "no data"
        return out

    latest = data[0] if isinstance(data[0], dict) else {}
    out.strong_buy = int(latest.get("strongBuy") or 0)
    out.buy = int(latest.get("buy") or 0)
    out.hold = int(latest.get("hold") or 0)
    out.sell = int(latest.get("sell") or 0)
    out.strong_sell = int(latest.get("strongSell") or 0)
    out.revision_proxy = _net_score(latest)

    if len(data) >= 2 and isinstance(data[1], dict):
        prev = _net_score(data[1])
        if out.revision_proxy is not None and prev is not None:
            delta = out.revision_proxy - prev
            if delta > 0.05:
                out.trend_label = "improving vs prior period"
            elif delta < -0.05:
                out.trend_label = "deteriorating vs prior period"
            else:
                out.trend_label = "stable vs prior period"
        else:
            out.trend_label = "latest period only"
    else:
        out.trend_label = "latest period only"

    return out
