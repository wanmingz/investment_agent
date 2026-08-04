"""Tests for stock research memo schemas."""

from investment_agent.stock_research.models import (
    BusinessReport,
    ExpectationReport,
    FinancialReport,
    InvestmentMemo,
    MemoRating,
    ReasoningOutput,
    ValuationReport,
)


def test_memo_rating_enum_values() -> None:
    assert MemoRating.BUY.value == "buy"
    assert set(MemoRating) == {
        MemoRating.BUY,
        MemoRating.HOLD,
        MemoRating.SELL,
        MemoRating.WATCH,
    }


def test_reasoning_output_roundtrip() -> None:
    out = ReasoningOutput(
        rating=MemoRating.HOLD,
        confidence=0.6,
        executive_summary="Balanced risk/reward.",
        investment_thesis="Quality franchise at fair value.",
        bull_case=["Margin expansion"],
        bear_case=["Multiple compression"],
        key_risks=["Competition"],
        catalysts=["Product cycle"],
        valuation_takeaway="Fair",
        expectation_takeaway="In line",
        monitoring_items=["Next earnings"],
    )
    assert out.rating == MemoRating.HOLD
    dumped = out.model_dump(mode="json")
    assert dumped["rating"] == "hold"


def test_investment_memo_attaches_domain_reports() -> None:
    biz = BusinessReport(
        company_overview="Consumer tech",
        business_model="Hardware + services",
        competitive_position="Strong brand",
        quality_score=0.8,
    )
    fin = FinancialReport(
        financial_summary="Solid FCF",
        growth_assessment="Mid-single digit",
        profitability_assessment="High margins",
        balance_sheet_assessment="Net cash",
        cash_flow_assessment="Strong",
        quality_of_earnings=0.75,
    )
    val = ValuationReport(
        valuation_summary="Around historical mean",
        multiples_view="Fwd PE mid-20s",
        absolute_vs_relative="Fair vs history",
        fair_value_view="Near fair",
        valuation_stance="fair",
        confidence=0.55,
    )
    exp = ExpectationReport(
        expectation_summary="Modest upside to Street",
        consensus_vs_price="Slightly below target",
        revision_trend="Stable",
        surprise_potential="Limited",
        confidence=0.5,
    )
    memo = InvestmentMemo(
        ticker="AAPL",
        company_name="Apple Inc.",
        rating=MemoRating.BUY,
        confidence=0.7,
        executive_summary="Constructive.",
        investment_thesis="Services mix supports quality.",
        business=biz,
        financial=fin,
        valuation=val,
        expectation=exp,
    )
    assert memo.business is not None
    assert memo.valuation.valuation_stance == "fair"
    assert memo.model_dump(mode="json")["ticker"] == "AAPL"
