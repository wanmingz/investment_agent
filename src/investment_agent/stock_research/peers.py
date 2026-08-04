"""Industry → peer tickers for relative valuation (stock research)."""

from __future__ import annotations

# Coarse industry/sector → 3–5 liquid peers (exclude subject ticker at fetch time).
INDUSTRY_PEERS: dict[str, tuple[str, ...]] = {
    "consumer electronics": ("AAPL", "SONY", "DELL", "HPQ"),
    "software": ("MSFT", "ORCL", "ADBE", "CRM", "NOW"),
    "software—infrastructure": ("MSFT", "ORCL", "CRWD", "PANW", "SNOW"),
    "software—application": ("CRM", "ADBE", "INTU", "NOW", "WDAY"),
    "semiconductors": ("NVDA", "AMD", "AVGO", "QCOM", "INTC"),
    "semiconductor equipment": ("ASML", "AMAT", "LRCX", "KLAC"),
    "internet content & information": ("GOOGL", "META", "SNAP", "PINS"),
    "internet retail": ("AMZN", "BABA", "MELI", "JD"),
    "banks": ("JPM", "BAC", "WFC", "C", "GS"),
    "banks—diversified": ("JPM", "BAC", "WFC", "C"),
    "capital markets": ("GS", "MS", "SCHW", "BLK"),
    "biotechnology": ("AMGN", "GILD", "VRTX", "REGN", "BIIB"),
    "drug manufacturers—general": ("JNJ", "PFE", "MRK", "LLY", "ABBV"),
    "oil & gas e&p": ("XOM", "CVX", "COP", "EOG", "PXD"),
    "oil & gas integrated": ("XOM", "CVX", "BP", "SHEL", "TTE"),
    "auto manufacturers": ("TSLA", "F", "GM", "TM", "RIVN"),
    "aerospace & defense": ("BA", "LMT", "RTX", "NOC", "GD"),
    "utilities—regulated electric": ("NEE", "DUK", "SO", "D", "AEP"),
    "reit": ("PLD", "AMT", "EQIX", "SPG", "O"),
}

SECTOR_PEERS: dict[str, tuple[str, ...]] = {
    "technology": ("MSFT", "AAPL", "NVDA", "AVGO", "ORCL"),
    "communication services": ("GOOGL", "META", "NFLX", "DIS", "T"),
    "consumer cyclical": ("AMZN", "TSLA", "HD", "MCD", "NKE"),
    "consumer defensive": ("PG", "KO", "PEP", "WMT", "COST"),
    "financial services": ("JPM", "BAC", "V", "MA", "BRK-B"),
    "healthcare": ("LLY", "UNH", "JNJ", "ABBV", "MRK"),
    "energy": ("XOM", "CVX", "COP", "SLB", "EOG"),
    "industrials": ("CAT", "GE", "HON", "UPS", "RTX"),
    "basic materials": ("LIN", "APD", "SHW", "ECL", "NEM"),
    "real estate": ("PLD", "AMT", "EQIX", "CCI", "SPG"),
    "utilities": ("NEE", "DUK", "SO", "D", "AEP"),
}


def peers_for(*, industry: str = "", sector: str = "", ticker: str = "") -> list[str]:
    """Return up to 5 peer symbols, excluding *ticker*."""
    sym = ticker.strip().upper()
    ind = (industry or "").strip().lower()
    sec = (sector or "").strip().lower()
    peers: tuple[str, ...] = ()
    if ind and ind in INDUSTRY_PEERS:
        peers = INDUSTRY_PEERS[ind]
    else:
        # fuzzy industry key contains match
        for key, vals in INDUSTRY_PEERS.items():
            if ind and (ind in key or key in ind):
                peers = vals
                break
    if not peers and sec:
        peers = SECTOR_PEERS.get(sec, ())
        if not peers:
            for key, vals in SECTOR_PEERS.items():
                if sec in key or key in sec:
                    peers = vals
                    break
    out = [p for p in peers if p.upper() != sym][:5]
    return out
