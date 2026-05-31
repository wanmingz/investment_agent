"""Optional live volatility context for the quant agent."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VolSnapshot:
    vix_level: float | None
    vix_20d_change_pct: float | None
    sector_vol: dict[str, float]
    notes: list[str]

    def to_prompt_block(self) -> str:
        lines = ["## Live volatility snapshot (yfinance)"]
        if self.vix_level is not None:
            lines.append(f"- VIX proxy (^VIX): {self.vix_level:.2f}")
        if self.vix_20d_change_pct is not None:
            lines.append(f"- VIX 20d change: {self.vix_20d_change_pct:+.1f}%")
        for sector, vol in self.sector_vol.items():
            lines.append(f"- {sector} 20d ann. vol: {vol:.1%}")
        if self.notes:
            lines.append("Notes: " + "; ".join(self.notes))
        return "\n".join(lines)


def fetch_vol_snapshot() -> VolSnapshot:
    notes: list[str] = []
    vix_level: float | None = None
    vix_change: float | None = None
    sector_vol: dict[str, float] = {}

    try:
        import yfinance as yf
    except ImportError:
        return VolSnapshot(None, None, {}, ["yfinance not installed"])

    tickers = {
        "VIX": "^VIX",
        "Tech": "XLK",
        "Energy": "XLE",
        "Healthcare": "XLV",
        "Financials": "XLF",
        "AI/Cloud": "IGV",
    }

    for label, symbol in tickers.items():
        try:
            hist = yf.Ticker(symbol).history(period="1mo")
            if hist.empty or len(hist) < 5:
                notes.append(f"{label}: insufficient data")
                continue
            returns = hist["Close"].pct_change().dropna()
            ann_vol = float(returns.std() * (252**0.5))
            if label == "VIX":
                vix_level = float(hist["Close"].iloc[-1])
                if len(hist) >= 20:
                    vix_change = float(
                        (hist["Close"].iloc[-1] / hist["Close"].iloc[-20] - 1) * 100
                    )
            else:
                sector_vol[label] = ann_vol
        except Exception as exc:  # noqa: BLE001 — best-effort market data
            notes.append(f"{label}: {exc}")

    return VolSnapshot(vix_level, vix_change, sector_vol, notes)
