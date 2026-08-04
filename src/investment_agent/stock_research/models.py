"""Pydantic schemas for single-stock research agents + investment memo."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class MemoRating(str, Enum):
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    WATCH = "watch"


class BusinessReport(BaseModel):
    """Business analysis agent output."""

    company_overview: str = Field(description="What the company does in 2-4 sentences")
    business_model: str = Field(description="How it makes money")
    competitive_position: str = Field(description="Moat, rivals, differentiation")
    key_segments: list[str] = Field(default_factory=list)
    catalysts: list[str] = Field(default_factory=list)
    business_risks: list[str] = Field(default_factory=list)
    quality_score: float = Field(ge=0, le=1, description="Business quality 0-1")


class FinancialReport(BaseModel):
    """Financial analysis agent output."""

    financial_summary: str
    growth_assessment: str
    profitability_assessment: str
    balance_sheet_assessment: str
    cash_flow_assessment: str
    financial_strengths: list[str] = Field(default_factory=list)
    financial_concerns: list[str] = Field(default_factory=list)
    quality_of_earnings: float = Field(ge=0, le=1)


class ValuationReport(BaseModel):
    """Valuation analysis agent output."""

    valuation_summary: str
    multiples_view: str
    absolute_vs_relative: str
    fair_value_view: str = Field(
        description="Qualitative fair-value take; cite only provided numbers"
    )
    valuation_stance: str = Field(description="cheap | fair | expensive | unclear")
    key_multiples_cited: list[str] = Field(default_factory=list)
    valuation_risks: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class ExpectationReport(BaseModel):
    """Market expectation / consensus agent output."""

    expectation_summary: str
    consensus_vs_price: str
    revision_trend: str
    surprise_potential: str
    implied_assumptions: list[str] = Field(default_factory=list)
    expectation_risks: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class ReasoningOutput(BaseModel):
    """Reasoning agent LLM output (domain reports attached by orchestrator)."""

    rating: MemoRating
    confidence: float = Field(ge=0, le=1)
    executive_summary: str
    investment_thesis: str
    bull_case: list[str] = Field(default_factory=list)
    bear_case: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    catalysts: list[str] = Field(default_factory=list)
    valuation_takeaway: str = ""
    expectation_takeaway: str = ""
    monitoring_items: list[str] = Field(default_factory=list)


class InvestmentMemo(BaseModel):
    """Persisted single-stock research memo."""

    ticker: str
    company_name: str = ""
    report_date: str = ""
    as_of_context: str = ""
    rating: MemoRating
    confidence: float = Field(ge=0, le=1)
    executive_summary: str
    investment_thesis: str
    bull_case: list[str] = Field(default_factory=list)
    bear_case: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    catalysts: list[str] = Field(default_factory=list)
    valuation_takeaway: str = ""
    expectation_takeaway: str = ""
    monitoring_items: list[str] = Field(default_factory=list)
    last_price: float | None = None
    data_sources: list[str] = Field(default_factory=list)
    business: BusinessReport | None = None
    financial: FinancialReport | None = None
    valuation: ValuationReport | None = None
    expectation: ExpectationReport | None = None
