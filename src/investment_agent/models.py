from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ThemeStage(str, Enum):
    EARLY = "early"
    EARLY_MID = "early_mid"
    MID = "mid"
    MID_LATE = "mid_late"
    LATE = "late"


STAGE_ORDER: tuple[ThemeStage, ...] = (
    ThemeStage.EARLY,
    ThemeStage.EARLY_MID,
    ThemeStage.MID,
    ThemeStage.MID_LATE,
    ThemeStage.LATE,
)

STAGE_LABELS: dict[str, str] = {
    "early": "Early",
    "early_mid": "Early-Mid",
    "mid": "Mid",
    "mid_late": "Mid-Late",
    "late": "Late",
}

# Backward compatibility
STAGE_LABELS_ZH = STAGE_LABELS


def coerce_theme_stage(value: str | ThemeStage) -> ThemeStage:
    if isinstance(value, ThemeStage):
        return value
    return ThemeStage(value)


def stage_label(value: str | ThemeStage, fallback: str = "") -> str:
    key = value.value if isinstance(value, ThemeStage) else str(value)
    return STAGE_LABELS.get(key, fallback or key)


stage_label_zh = stage_label


class AgentTheme(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(description="Investment theme name in English")
    subtitle: str = Field(
        default="",
        alias="name_zh",
        description="Optional short subtitle",
    )
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
    model_config = ConfigDict(populate_by_name=True)

    name: str
    subtitle: str = Field(default="", alias="name_zh")
    thesis: str
    stage: ThemeStage
    stage_label: str = Field(default="", alias="stage_label_zh")
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
    report_date: str = Field(
        default="",
        description="Analysis date in ISO format YYYY-MM-DD (local calendar day)",
    )
    as_of_context: str
    executive_summary: str
    macro_view: str
    equity_view: str
    quant_view: str
    themes: list[FinalTheme]
    disclaimer: str = (
        "For research purposes only. Not investment advice. "
        "Make your own decisions based on your risk tolerance."
    )
