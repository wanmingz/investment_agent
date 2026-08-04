"""Tests for stock research orchestrator with mocked LLM."""

from datetime import date
from unittest.mock import MagicMock

from investment_agent.config import Settings
from investment_agent.stock_research.bundle import StockBundle
from investment_agent.stock_research.models import (
    BusinessReport,
    ExpectationReport,
    FinancialReport,
    MemoRating,
    ReasoningOutput,
    ValuationReport,
)
from investment_agent.stock_research.orchestrator import StockResearchOrchestrator
from investment_agent.stock_research.storage import load_memo, save_run_reports


def _fake_settings() -> Settings:
    return Settings(
        api_key="test",
        base_url="https://api.openai.com/v1",
        model="gpt-4o",
        market_region="global",
        provider="openai",
        finnhub_api_key="",
        llm_parallel_agents=False,
        llm_agent_delay_seconds=0.0,
    )


def _bundle() -> StockBundle:
    return StockBundle(
        ticker="AAA",
        as_of=date(2026, 8, 4),
        company_name="AAA Inc",
        last_price=10.0,
        business_block="biz",
        financial_block="fin",
        valuation_block="val",
        expectation_block="exp",
        notes=["note"],
    )


def test_orchestrator_calls_five_agents_and_saves(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "investment_agent.stock_research.storage.REPORT_DIR",
        tmp_path / "stock_research",
    )
    monkeypatch.setattr(
        "investment_agent.stock_research.storage.RUNS_DIR",
        tmp_path / "stock_research" / "runs",
    )
    monkeypatch.setattr(
        "investment_agent.stock_research.checkpoint.CACHE_ROOT",
        tmp_path / "cache",
    )
    monkeypatch.setattr(
        "investment_agent.stock_research.orchestrator.fetch_stock_bundle",
        lambda *a, **k: _bundle(),
    )
    monkeypatch.setattr(
        "investment_agent.stock_research.orchestrator.analysis_date",
        lambda: date(2026, 8, 4),
    )

    biz = BusinessReport(
        company_overview="o",
        business_model="m",
        competitive_position="c",
        quality_score=0.7,
    )
    fin = FinancialReport(
        financial_summary="s",
        growth_assessment="g",
        profitability_assessment="p",
        balance_sheet_assessment="b",
        cash_flow_assessment="cf",
        quality_of_earnings=0.6,
    )
    val = ValuationReport(
        valuation_summary="vs",
        multiples_view="mv",
        absolute_vs_relative="avr",
        fair_value_view="fv",
        valuation_stance="fair",
        confidence=0.5,
    )
    exp = ExpectationReport(
        expectation_summary="es",
        consensus_vs_price="cvp",
        revision_trend="stable",
        surprise_potential="low",
        confidence=0.4,
    )
    reason = ReasoningOutput(
        rating=MemoRating.WATCH,
        confidence=0.55,
        executive_summary="Watch for better entry.",
        investment_thesis="Quality but wait.",
        bull_case=["Upside optionality"],
        bear_case=["Rich multiple"],
        key_risks=["Execution"],
        catalysts=["Guide raise"],
    )

    call_order: list[str] = []

    def structured(*, system, user, schema):  # noqa: ANN001
        name = schema.__name__
        call_order.append(name)
        mapping = {
            "BusinessReport": biz,
            "FinancialReport": fin,
            "ValuationReport": val,
            "ExpectationReport": exp,
            "ReasoningOutput": reason,
        }
        return mapping[name]

    orch = StockResearchOrchestrator(_fake_settings())
    orch._llm = MagicMock()
    orch._llm.structured.side_effect = structured
    orch._business = type(orch._business)(orch._llm)
    orch._financial = type(orch._financial)(orch._llm)
    orch._valuation = type(orch._valuation)(orch._llm)
    orch._expectation = type(orch._expectation)(orch._llm)
    orch._reasoning = type(orch._reasoning)(orch._llm)

    memo = orch.run("aaa", resume=False)
    assert memo.ticker == "AAA"
    assert memo.rating == MemoRating.WATCH
    assert memo.business is not None
    assert call_order == [
        "BusinessReport",
        "FinancialReport",
        "ValuationReport",
        "ExpectationReport",
        "ReasoningOutput",
    ]

    latest, archive = save_run_reports(memo)
    assert latest.is_file()
    assert archive.is_file()
    loaded = load_memo("AAA")
    assert loaded is not None
    assert loaded.executive_summary == "Watch for better entry."
