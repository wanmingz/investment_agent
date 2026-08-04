"""Orchestrate 4 domain agents + reasoning → InvestmentMemo."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from investment_agent.config import Settings
from investment_agent.dates import analysis_date, build_as_of_context, format_date_iso
from investment_agent.llm import LLMClient
from investment_agent.stock_research import checkpoint
from investment_agent.stock_research.bundle import StockBundle, fetch_stock_bundle
from investment_agent.stock_research.business import BusinessAgent, build_business_input
from investment_agent.stock_research.expectation import ExpectationAgent, build_expectation_input
from investment_agent.stock_research.financial import FinancialAgent, build_financial_input
from investment_agent.stock_research.models import (
    BusinessReport,
    ExpectationReport,
    FinancialReport,
    InvestmentMemo,
    ValuationReport,
)
from investment_agent.stock_research.reasoning import ReasoningAgent
from investment_agent.stock_research.valuation import ValuationAgent, build_valuation_input


class StockResearchOrchestrator:
    def __init__(self, settings: Settings | None = None):
        self._settings = settings or Settings.from_env()
        self._llm = LLMClient(self._settings)
        self._business = BusinessAgent(self._llm)
        self._financial = FinancialAgent(self._llm)
        self._valuation = ValuationAgent(self._llm)
        self._expectation = ExpectationAgent(self._llm)
        self._reasoning = ReasoningAgent(self._llm)

    def run(self, ticker: str, *, resume: bool | None = None) -> InvestmentMemo:
        sym = ticker.strip().upper()
        as_of = analysis_date()
        use_resume = resume if resume is not None else checkpoint.is_resume_enabled()

        if use_resume and not checkpoint.meta_matches(ticker=sym, as_of=as_of):
            checkpoint.clear_checkpoint(sym)
        if use_resume:
            checkpoint.save_run_meta(ticker=sym, as_of=as_of)

        bundle = checkpoint.load_bundle(sym) if use_resume else None
        if bundle is None:
            bundle = fetch_stock_bundle(sym, settings=self._settings, as_of=as_of)
            if use_resume:
                checkpoint.save_bundle(bundle)

        business = checkpoint.load_business(sym) if use_resume else None
        financial = checkpoint.load_financial(sym) if use_resume else None
        valuation = checkpoint.load_valuation(sym) if use_resume else None
        expectation = checkpoint.load_expectation(sym) if use_resume else None

        business, financial, valuation, expectation = self._run_domain_agents(
            bundle=bundle,
            business=business,
            financial=financial,
            valuation=valuation,
            expectation=expectation,
            use_resume=use_resume,
        )

        assert business and financial and valuation and expectation
        reasoning = self._reasoning.analyze(
            ticker=bundle.ticker,
            company_name=bundle.company_name,
            as_of=as_of,
            last_price=bundle.last_price,
            business=business,
            financial=financial,
            valuation=valuation,
            expectation=expectation,
        )

        sources = [
            f"LLM ({self._settings.provider}/{self._settings.model}) — "
            "business, financial, valuation, expectation, reasoning",
            "yfinance — company info, financials, multiples, targets",
            "TickerTick — optional company headlines",
        ]
        if self._settings.finnhub_api_key:
            sources.append("Finnhub — recommendation trend proxy")
        if bundle.notes:
            sources.append("Fetch notes: " + "; ".join(bundle.notes[:6]))

        memo = InvestmentMemo(
            ticker=bundle.ticker,
            company_name=bundle.company_name,
            report_date=format_date_iso(as_of),
            as_of_context=build_as_of_context("", as_of=as_of),
            rating=reasoning.rating,
            confidence=reasoning.confidence,
            executive_summary=reasoning.executive_summary,
            investment_thesis=reasoning.investment_thesis,
            bull_case=list(reasoning.bull_case),
            bear_case=list(reasoning.bear_case),
            key_risks=list(reasoning.key_risks),
            catalysts=list(reasoning.catalysts),
            valuation_takeaway=reasoning.valuation_takeaway,
            expectation_takeaway=reasoning.expectation_takeaway,
            monitoring_items=list(reasoning.monitoring_items),
            last_price=bundle.last_price,
            data_sources=sources,
            business=business,
            financial=financial,
            valuation=valuation,
            expectation=expectation,
        )
        if use_resume:
            checkpoint.clear_checkpoint(sym)
        return memo

    def _run_domain_agents(
        self,
        *,
        bundle: StockBundle,
        business: BusinessReport | None,
        financial: FinancialReport | None,
        valuation: ValuationReport | None,
        expectation: ExpectationReport | None,
        use_resume: bool,
    ) -> tuple[
        BusinessReport | None,
        FinancialReport | None,
        ValuationReport | None,
        ExpectationReport | None,
    ]:
        tasks: list[tuple[str, object]] = []
        if business is None:
            tasks.append(("business", build_business_input(bundle)))
        if financial is None:
            tasks.append(("financial", build_financial_input(bundle)))
        if valuation is None:
            tasks.append(("valuation", build_valuation_input(bundle)))
        if expectation is None:
            tasks.append(("expectation", build_expectation_input(bundle)))

        delay = self._settings.llm_agent_delay_seconds
        sym = bundle.ticker

        def _save(key: str, result: object) -> None:
            nonlocal business, financial, valuation, expectation
            if key == "business":
                business = result  # type: ignore[assignment]
                if use_resume:
                    checkpoint.save_business(sym, business)  # type: ignore[arg-type]
            elif key == "financial":
                financial = result  # type: ignore[assignment]
                if use_resume:
                    checkpoint.save_financial(sym, financial)  # type: ignore[arg-type]
            elif key == "valuation":
                valuation = result  # type: ignore[assignment]
                if use_resume:
                    checkpoint.save_valuation(sym, valuation)  # type: ignore[arg-type]
            else:
                expectation = result  # type: ignore[assignment]
                if use_resume:
                    checkpoint.save_expectation(sym, expectation)  # type: ignore[arg-type]

        def _analyze(key: str, agent_input: object) -> object:
            if key == "business":
                return self._business.analyze(agent_input)  # type: ignore[arg-type]
            if key == "financial":
                return self._financial.analyze(agent_input)  # type: ignore[arg-type]
            if key == "valuation":
                return self._valuation.analyze(agent_input)  # type: ignore[arg-type]
            return self._expectation.analyze(agent_input)  # type: ignore[arg-type]

        if not tasks:
            return business, financial, valuation, expectation

        if self._settings.llm_parallel_agents and len(tasks) > 1:
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = {
                    pool.submit(_analyze, key, agent_input): key for key, agent_input in tasks
                }
                for fut in as_completed(futures):
                    key = futures[fut]
                    _save(key, fut.result())
            return business, financial, valuation, expectation

        for i, (key, agent_input) in enumerate(tasks):
            if i > 0 and delay > 0:
                time.sleep(delay)
            _save(key, _analyze(key, agent_input))
        return business, financial, valuation, expectation
