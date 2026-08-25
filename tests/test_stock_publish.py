"""Tests for publishing stock memos to brief/ for Streamlit Cloud."""

from pathlib import Path

import pytest

from investment_agent.stock_research.models import (
    BusinessReport,
    ExpectationReport,
    FinancialReport,
    InvestmentMemo,
    MemoRating,
    ValuationReport,
)
from investment_agent.stock_research.publish import load_published, publish_memo
from investment_agent.stock_research.storage import (
    latest_path,
    load_memo,
    published_path,
    save_memo,
)


def _sample_memo(ticker: str = "AAPL") -> InvestmentMemo:
    return InvestmentMemo(
        ticker=ticker,
        company_name="Apple Inc.",
        rating=MemoRating.HOLD,
        confidence=0.65,
        executive_summary="Example memo for Cloud friends.",
        investment_thesis="Services mix supports quality at a fair multiple.",
        business=BusinessReport(
            company_overview="Consumer electronics and services.",
            business_model="Hardware + services.",
            competitive_position="Strong brand and ecosystem.",
            quality_score=0.85,
        ),
        financial=FinancialReport(
            financial_summary="High FCF.",
            growth_assessment="Mid-single digit.",
            profitability_assessment="High margins.",
            balance_sheet_assessment="Net cash.",
            cash_flow_assessment="Strong.",
            quality_of_earnings=0.8,
        ),
        valuation=ValuationReport(
            valuation_summary="Near fair.",
            multiples_view="Fwd PE mid-20s.",
            absolute_vs_relative="Fair vs history.",
            fair_value_view="Around fair value.",
            valuation_stance="fair",
            confidence=0.6,
        ),
        expectation=ExpectationReport(
            expectation_summary="In line with Street.",
            consensus_vs_price="Near target.",
            revision_trend="Stable.",
            surprise_potential="Limited.",
            confidence=0.55,
        ),
    )


def test_publish_and_load_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reports = tmp_path / "reports" / "stock_research"
    brief = tmp_path / "brief"
    reports.mkdir(parents=True)
    brief.mkdir(parents=True)

    monkeypatch.setattr(
        "investment_agent.stock_research.storage.REPORT_DIR", reports
    )
    monkeypatch.setattr(
        "investment_agent.stock_research.storage.BRIEF_DIR", brief
    )
    monkeypatch.setattr(
        "investment_agent.stock_research.storage.RUNS_DIR", reports / "runs"
    )

    memo = _sample_memo()
    save_memo(memo)
    assert latest_path("AAPL").is_file()

    out = publish_memo("AAPL")
    assert out == published_path("AAPL")
    assert out.is_file()

    # Cloud-like: no local reports file
    latest_path("AAPL").unlink()
    loaded = load_memo("AAPL")
    assert loaded is not None
    assert loaded.ticker == "AAPL"
    assert loaded.executive_summary.startswith("Example")

    published = load_published("AAPL")
    assert published is not None
    assert published.rating == MemoRating.HOLD


def test_publish_requires_local_memo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reports = tmp_path / "reports" / "stock_research"
    brief = tmp_path / "brief"
    reports.mkdir(parents=True)
    brief.mkdir(parents=True)
    monkeypatch.setattr(
        "investment_agent.stock_research.storage.REPORT_DIR", reports
    )
    monkeypatch.setattr(
        "investment_agent.stock_research.storage.BRIEF_DIR", brief
    )
    with pytest.raises(ValueError, match="No saved memo"):
        publish_memo("AAPL")
