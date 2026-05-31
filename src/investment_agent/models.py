from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ThemeStage(str, Enum):
    EARLY = "early"
    MID = "mid"
    LATE = "late"


class AgentTheme(BaseModel):
    name: str = Field(description="Investment theme name (English or bilingual)")
    name_zh: str = Field(default="", description="Chinese name if applicable")
    thesis: str = Field(description="Why this theme matters now")
    stage: ThemeStage
    stage_rationale: str
    confidence: float = Field(ge=0, le=1)
    key_drivers: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    tickers_or_sectors: list[str] = Field(default_factory=list)


class MacroReport(BaseModel):
    macro_backdrop: str
    dominant_regime: str
    themes: list[AgentTheme]
    cross_asset_signals: list[str] = Field(default_factory=list)


class EquityReport(BaseModel):
    market_style: str
    themes: list[AgentTheme]
    valuation_notes: list[str] = Field(default_factory=list)


class QuantReport(BaseModel):
    vol_regime: Literal["low", "normal", "elevated", "crisis"]
    vix_proxy_level: float | None = None
    themes: list[AgentTheme]
    vol_signals: list[str] = Field(default_factory=list)


class FinalTheme(BaseModel):
    name: str
    name_zh: str
    thesis: str
    stage: ThemeStage
    stage_label_zh: str
    consensus_score: float = Field(
        description="0-1 agreement across agents on stage classification"
    )
    investability_score: float = Field(
        ge=0, le=1, description="Combined attractiveness now"
    )
    agent_stages: dict[str, ThemeStage]
    synthesis: str
    key_drivers: list[str]
    risks: list[str]
    tickers_or_sectors: list[str]


class InvestmentBrief(BaseModel):
    as_of_context: str
    executive_summary: str
    macro_view: str
    equity_view: str
    quant_view: str
    themes: list[FinalTheme]
    disclaimer: str = (
        "本输出仅供研究参考，不构成投资建议。请结合自身风险承受能力独立决策。"
    )
