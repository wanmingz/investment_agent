"""Aggregate structured fundamentals for the equity agent."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date

from investment_agent.data.price import PriceMetrics, fetch_price_metrics
from investment_agent.data.revisions import RevisionMetrics, fetch_revision_metrics
from investment_agent.data.universe import (
    BENCHMARK_SYMBOL,
    SECTOR_ETFS,
    extract_tickers_from_themes,
    symbols_for_fundamentals,
)
from investment_agent.data.valuation import ValuationMetrics, fetch_valuation_metrics
from investment_agent.models import AgentTheme

_ETF_SYMBOLS = set(SECTOR_ETFS.values()) | {BENCHMARK_SYMBOL}


@dataclass
class SymbolFundamentals:
    label: str
    symbol: str
    price: PriceMetrics
    valuation: ValuationMetrics
    revision: RevisionMetrics | None = None


@dataclass
class FundamentalsSnapshot:
    as_of: str
    rows: list[SymbolFundamentals] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_prompt_block(self) -> str:
        lines = [
            "## Structured fundamentals (yfinance + optional Finnhub revision proxy)",
            f"As-of: {self.as_of}",
            "Use ONLY these numbers for valuation/return/revision claims — do not invent metrics.",
        ]
        if self.signals:
            lines.append("\n### Structured hints (rule-based, not investment advice)")
            for s in self.signals:
                lines.append(f"- {s}")
        lines.append("\n### Per-symbol metrics")
        for row in self.rows:
            p, v = row.price, row.valuation
            parts = [f"\n**{row.label} ({row.symbol})**"]
            if p.last_close is not None:
                parts.append(f"last={p.last_close:.2f}")
            if p.return_20d_pct is not None:
                parts.append(f"20d_return={p.return_20d_pct:+.1f}%")
            if p.return_60d_pct is not None:
                parts.append(f"60d_return={p.return_60d_pct:+.1f}%")
            if p.pct_from_52w_high is not None:
                parts.append(f"vs_52w_high={p.pct_from_52w_high:+.1f}%")
            if p.vs_spy_20d_pct is not None:
                parts.append(f"vs_SPY_20d={p.vs_spy_20d_pct:+.1f}pp")
            if v.forward_pe is not None:
                parts.append(f"fwd_P/E={v.forward_pe:.1f}")
            elif v.trailing_pe is not None:
                parts.append(f"trail_P/E={v.trailing_pe:.1f}")
            if v.price_to_book is not None:
                parts.append(f"P/B={v.price_to_book:.2f}")
            if row.revision and row.revision.revision_proxy is not None:
                parts.append(
                    f"revision_proxy={row.revision.revision_proxy:+.2f} ({row.revision.trend_label})"
                )
            lines.append(" | ".join(parts))
        if self.notes:
            lines.append("\n### Data notes")
            for n in self.notes:
                lines.append(f"- {n}")
        return "\n".join(lines)

    def summary_lines(self) -> list[str]:
        """Short bullets for InvestmentBrief.fundamentals_notes."""
        out: list[str] = []
        for row in self.rows[:6]:
            p = row.price
            v = row.valuation
            chunk = f"{row.label} ({row.symbol})"
            if p.return_20d_pct is not None:
                chunk += f" 20d {p.return_20d_pct:+.1f}%"
            if v.forward_pe is not None:
                chunk += f" fwd P/E {v.forward_pe:.1f}"
            out.append(chunk)
        out.extend(self.signals[:4])
        return out


def _build_signals(rows: list[SymbolFundamentals]) -> list[str]:
    signals: list[str] = []
    spy = next((r for r in rows if r.symbol == BENCHMARK_SYMBOL), None)
    for row in rows:
        if row.symbol in _ETF_SYMBOLS and row.symbol != BENCHMARK_SYMBOL:
            p = row.price
            if p.return_20d_pct is not None and p.return_20d_pct > 5:
                signals.append(f"{row.label}: strong 20d momentum ({p.return_20d_pct:+.1f}%)")
            if p.pct_from_52w_high is not None and p.pct_from_52w_high > -2:
                signals.append(f"{row.label}: near 52-week high ({p.pct_from_52w_high:+.1f}% vs high)")
            v = row.valuation
            if v.forward_pe is not None and v.forward_pe > 25:
                signals.append(f"{row.label}: elevated forward P/E ({v.forward_pe:.1f})")
            if (
                spy
                and p.vs_spy_20d_pct is not None
                and p.vs_spy_20d_pct > 3
            ):
                signals.append(
                    f"{row.label}: outperforming SPY 20d by {p.vs_spy_20d_pct:+.1f}pp"
                )
        rev = row.revision
        if rev and rev.revision_proxy is not None:
            if rev.revision_proxy > 0.25:
                signals.append(
                    f"{row.symbol}: positive revision proxy ({rev.revision_proxy:+.2f})"
                )
            elif rev.revision_proxy < -0.25:
                signals.append(
                    f"{row.symbol}: negative revision proxy ({rev.revision_proxy:+.2f})"
                )
    return signals[:12]


def _fetch_one(
    label: str,
    symbol: str,
    *,
    spy_return_20d: float | None,
    finnhub_key: str,
    fetch_revision: bool,
) -> SymbolFundamentals:
    price = fetch_price_metrics(symbol, label=label, spy_return_20d=spy_return_20d)
    valuation = fetch_valuation_metrics(symbol, label=label)
    revision = None
    if fetch_revision:
        revision = fetch_revision_metrics(
            symbol, label=label, finnhub_key=finnhub_key
        )
    return SymbolFundamentals(
        label=label,
        symbol=symbol.upper(),
        price=price,
        valuation=valuation,
        revision=revision,
    )


def fetch_fundamentals_snapshot(
    themes: list[AgentTheme],
    *,
    as_of: date | None = None,
    finnhub_key: str = "",
    max_extra_tickers: int | None = None,
) -> FundamentalsSnapshot:
    as_of = as_of or date.today()
    max_extra = max_extra_tickers or int(os.getenv("FUNDAMENTALS_MAX_TICKERS", "8"))

    theme_tickers: list[str] = []
    for th in themes:
        theme_tickers.extend(extract_tickers_from_themes(th.tickers_or_sectors))

    labeled, notes = symbols_for_fundamentals(theme_tickers, max_extra=max_extra)

    spy_row = fetch_price_metrics(BENCHMARK_SYMBOL, label="Benchmark")
    spy_return_20d = spy_row.return_20d_pct

    rows: list[SymbolFundamentals] = []
    workers = min(6, max(1, len(labeled)))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {}
        for label, sym in labeled:
            fetch_rev = sym not in _ETF_SYMBOLS and bool(finnhub_key)
            fut = pool.submit(
                _fetch_one,
                label,
                sym,
                spy_return_20d=spy_return_20d,
                finnhub_key=finnhub_key,
                fetch_revision=fetch_rev,
            )
            futures[fut] = sym

        for fut in as_completed(futures):
            try:
                rows.append(fut.result())
            except Exception as exc:  # noqa: BLE001
                sym = futures[fut]
                notes.append(f"{sym}: {exc}")

    rows.sort(key=lambda r: (0 if r.symbol in _ETF_SYMBOLS else 1, r.label))

    if not finnhub_key:
        notes.append("Finnhub revision proxy skipped (no FINNHUB_API_KEY)")
    else:
        notes.append(
            "Revision proxy = net (buy-strong_buy - sell-strong_sell) / total from Finnhub recommendation"
        )
    notes.append("Valuation/price via yfinance — delayed, not for trading")

    snapshot = FundamentalsSnapshot(
        as_of=as_of.isoformat(),
        rows=rows,
        signals=_build_signals(rows),
        notes=notes,
    )
    return snapshot


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
