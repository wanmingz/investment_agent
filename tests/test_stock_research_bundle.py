"""Tests for stock research data bundle slicing (P0 enrichment)."""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd

from investment_agent.config import Settings
from investment_agent.stock_research.bundle import (
    _yoy_lines,
    fetch_stock_bundle,
)
from investment_agent.stock_research.business import build_business_input
from investment_agent.stock_research.expectation import build_expectation_input
from investment_agent.stock_research.financial import build_financial_input
from investment_agent.stock_research.peers import peers_for
from investment_agent.stock_research.valuation import build_valuation_input


def _fake_settings() -> Settings:
    return Settings(
        api_key="test",
        base_url="https://api.openai.com/v1",
        model="gpt-4o",
        market_region="global",
        provider="openai",
        finnhub_api_key="",
        llm_parallel_agents=False,
    )


def test_peers_for_industry_and_excludes_self() -> None:
    peers = peers_for(industry="Semiconductors", sector="Technology", ticker="NVDA")
    assert "NVDA" not in peers
    assert "AMD" in peers
    assert len(peers) <= 5


def test_yoy_lines_computes_pct() -> None:
    # newest-first columns; YoY compares col i vs i+4
    cols = [f"Q{i}" for i in range(8)]
    # Q0=110 vs Q4=100 → +10%; others n/a if no base
    data = {c: [100.0 + (10 if i == 0 else 0)] for i, c in enumerate(cols)}
    # clearer: set each col explicitly
    values = [110, 105, 102, 101, 100, 98, 95, 90]
    df = pd.DataFrame({"Total Revenue": values}, index=cols).T
    # Wait - yfinance has rows as index and dates as columns
    df = pd.DataFrame(
        [values],
        index=["Total Revenue"],
        columns=cols,
    )
    lines = _yoy_lines(df, ["Total Revenue"], max_cols=8)
    assert lines
    assert "10.0%" in lines[0]  # 110/100 - 1


def test_fetch_stock_bundle_p0_enrichment(monkeypatch) -> None:
    monkeypatch.setenv("STOCK_RESEARCH_CONTEXT_MAX_CHARS", "8000")
    monkeypatch.setenv("STOCK_RESEARCH_NEWS_HEADLINES", "3")

    income = pd.DataFrame(
        {"2024": [100.0, 20.0], "2023": [90.0, 18.0]},
        index=["Total Revenue", "Net Income"],
    )
    cashflow = pd.DataFrame({"2024": [30.0]}, index=["Operating Cash Flow"])
    balance = pd.DataFrame({"2024": [200.0]}, index=["Total Assets"])

    q_cols = [datetime(2024, 12, 31), datetime(2024, 9, 30), datetime(2024, 6, 30), datetime(2024, 3, 31),
              datetime(2023, 12, 31), datetime(2023, 9, 30), datetime(2023, 6, 30), datetime(2023, 3, 31)]
    q_rev = [40, 38, 36, 35, 32, 30, 28, 27]
    q_income = pd.DataFrame(
        [q_rev, [2.0] * 8],
        index=["Total Revenue", "Diluted EPS"],
        columns=q_cols,
    )
    q_cashflow = pd.DataFrame([q_rev], index=["Operating Cash Flow"], columns=q_cols)
    q_balance = pd.DataFrame([[500] * 8], index=["Total Assets"], columns=q_cols)

    idx = pd.date_range("2020-01-01", periods=60, freq="ME")
    price_hist = pd.DataFrame({"Close": [40 + i * 0.1 for i in range(60)]}, index=idx)

    earnings_history = pd.DataFrame(
        {"epsActual": [1.1, 1.0], "epsEstimate": [1.0, 0.95]},
        index=["2024Q4", "2024Q3"],
    )
    earnings_dates = pd.DataFrame({"EPS Estimate": [1.2]}, index=["2025-01-30"])
    earnings_estimate = pd.DataFrame({"avg": [1.25], "low": [1.1], "high": [1.4]})
    revenue_estimate = pd.DataFrame({"avg": [1e9], "low": [0.9e9], "high": [1.1e9]})

    ticker = MagicMock()
    ticker.info = {
        "longName": "Test Corp",
        "longBusinessSummary": "Makes widgets.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "country": "United States",
        "fullTimeEmployees": 1000,
        "website": "https://example.com",
        "currentPrice": 50.0,
        "trailingPE": 20.0,
        "forwardPE": 18.0,
        "priceToBook": 5.0,
        "marketCap": 5e9,
        "sharesOutstanding": 1e8,
        "priceToSalesTrailing12Months": 4.0,
        "targetMeanPrice": 60.0,
        "targetHighPrice": 70.0,
        "targetLowPrice": 45.0,
        "recommendationKey": "buy",
        "revenueGrowth": 0.1,
        "earningsGrowth": 0.08,
        "grossMargins": 0.4,
        "operatingMargins": 0.2,
        "profitMargins": 0.15,
        "freeCashflow": 1e9,
        "operatingCashflow": 1.2e9,
    }
    ticker.income_stmt = income
    ticker.cashflow = cashflow
    ticker.balance_sheet = balance
    ticker.quarterly_income_stmt = q_income
    ticker.quarterly_cashflow = q_cashflow
    ticker.quarterly_balance_sheet = q_balance
    ticker.history.return_value = price_hist
    ticker.earnings_history = earnings_history
    ticker.earnings_dates = earnings_dates
    ticker.earnings_estimate = earnings_estimate
    ticker.revenue_estimate = revenue_estimate

    yf_mod = SimpleNamespace(Ticker=MagicMock(return_value=ticker))

    peer_vm = SimpleNamespace(
        trailing_pe=22.0, forward_pe=19.0, price_to_book=4.0, market_cap_b=10.0
    )

    with (
        patch.dict("sys.modules", {"yfinance": yf_mod}),
        patch(
            "investment_agent.stock_research.bundle.fetch_valuation_metrics",
            return_value=SimpleNamespace(
                trailing_pe=20.0,
                forward_pe=18.0,
                price_to_book=5.0,
                market_cap_b=5.0,
            ),
        ) as val_mock,
        patch(
            "investment_agent.stock_research.bundle.fetch_revision_metrics",
            return_value=SimpleNamespace(
                revision_proxy=0.2,
                trend_label="stable",
                strong_buy=2,
                buy=5,
                hold=3,
                sell=0,
                strong_sell=0,
            ),
        ),
        patch(
            "investment_agent.stock_research.bundle._fetch_ticker_news",
            return_value=(
                ["Widget demand rises — Supply chain easing in Asia"],
                ["tickertick:1"],
            ),
        ),
        patch(
            "investment_agent.stock_research.bundle._peer_multiple_lines",
            return_value=["Peer set: AAPL, SONY", "AAPL: PE(ttm)=25.0"],
        ),
    ):
        # subject valuation uses patched fetch; peers use _peer_multiple_lines mock
        _ = val_mock
        bundle = fetch_stock_bundle(
            "test",
            settings=_fake_settings(),
            as_of=date(2026, 8, 4),
        )

    assert bundle.ticker == "TEST"
    assert "Makes widgets" in bundle.business_block
    assert "Supply chain easing" in bundle.business_block
    assert "Quarterly income" in bundle.financial_block
    assert "YoY" in bundle.financial_block
    assert "Historical" in bundle.valuation_block or "percentile" in bundle.valuation_block
    assert "Peer" in bundle.valuation_block
    assert "Earnings estimate" in bundle.expectation_block
    assert "Revenue estimate" in bundle.expectation_block
    assert "Earnings history" in bundle.expectation_block
    assert len(bundle.business_block) <= 8000

    assert build_business_input(bundle).context_block == bundle.business_block
    assert build_financial_input(bundle).ticker == "TEST"
    assert build_valuation_input(bundle).last_price == 50.0
    assert "Target mean" in build_expectation_input(bundle).context_block
