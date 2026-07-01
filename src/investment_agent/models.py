from enum import Enum
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

AGENT_REGIME = "regime"
AGENT_NARRATIVE = "narrative"
AGENT_MARKETS = "markets"

AGENT_LABELS: dict[str, str] = {
    AGENT_REGIME: "Regime",
    AGENT_NARRATIVE: "Narrative",
    AGENT_MARKETS: "Markets",
}


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

    name: str = Field(description="Investment theme name in English only")
    subtitle: str = Field(
        default="",
        description="Optional short English tag; leave empty if unused",
        validation_alias=AliasChoices("subtitle", "name_zh"),
    )
    thesis: str = Field(description="Why this theme matters now")
    stage: ThemeStage
    stage_rationale: str
    confidence: float = Field(ge=0, le=1)
    key_drivers: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    tickers_or_sectors: list[str] = Field(default_factory=list)


class NewsCitation(BaseModel):
    id: str
    title: str
    source: str
    url: str
    published_at: str = ""


class SourcedItem(BaseModel):
    text: str
    citation_ids: list[str] = Field(default_factory=list)


class RegimeReport(BaseModel):
    """Regime agent output."""

    regime_backdrop: str
    dominant_regime: str
    themes: list[AgentTheme]
    cross_asset_signals: list[str] = Field(default_factory=list)


class NarrativeReport(BaseModel):
    """Narrative agent output (headline RAG)."""

    narrative_backdrop: str
    narrative_sentiment: Literal["risk-on", "neutral", "risk-off"] = "neutral"
    retrieval_query: str = ""
    articles_retrieved: int = 0
    ingest_notes: list[str] = Field(default_factory=list)
    citations: list[NewsCitation] = Field(default_factory=list)
    narrative_signals: list[str] = Field(default_factory=list)
    key_drivers_sourced: list[SourcedItem] = Field(default_factory=list)
    risks_sourced: list[SourcedItem] = Field(default_factory=list)
    themes: list[AgentTheme] = Field(default_factory=list)


class MarketsReport(BaseModel):
    """Markets agent output (fundamentals + vol lenses)."""

    market_style: str
    vol_regime: Literal["low", "normal", "elevated", "crisis"]
    vix_proxy_level: float | None = None
    fundamentals_view: str = ""
    vol_view: str = ""
    fundamentals_themes: list[AgentTheme] = Field(default_factory=list)
    vol_themes: list[AgentTheme] = Field(default_factory=list)
    valuation_notes: list[str] = Field(default_factory=list)
    vol_signals: list[str] = Field(default_factory=list)


class FinalTheme(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(description="Investment theme name in English only")
    subtitle: str = Field(
        default="",
        description="Optional short English tag; leave empty if unused",
        validation_alias=AliasChoices("subtitle", "name_zh"),
    )
    thesis: str = Field(description="Why this theme matters now (English only)")
    stage: ThemeStage
    stage_label: str = Field(
        default="",
        description="Human-readable stage label in English",
        validation_alias=AliasChoices("stage_label", "stage_label_zh"),
    )
    consensus_score: float = Field(
        description="0-1 agreement across agents on stage classification"
    )
    investability_score: float = Field(
        ge=0, le=1, description="Combined attractiveness now"
    )
    agent_stages: dict[str, ThemeStage] = Field(
        default_factory=dict,
        description="Stages per agent (regime, narrative, markets)",
    )
    contributing_agents: list[str] = Field(
        default_factory=list,
        description="Agents that listed this theme: regime, narrative, markets",
    )
    primary_agent: str = Field(
        default="",
        description="Agent that most strongly originated this theme",
    )
    synthesis: str
    key_drivers: list[str]
    risks: list[str]
    tickers_or_sectors: list[str]
    key_drivers_sourced: list[SourcedItem] = Field(default_factory=list)
    risks_sourced: list[SourcedItem] = Field(default_factory=list)


class InvestmentBrief(BaseModel):
    report_date: str = Field(
        default="",
        description="Analysis date in ISO format YYYY-MM-DD (local calendar day)",
    )
    as_of_context: str
    executive_summary: str
    regime_view: str
    narrative_view: str = ""
    markets_fundamentals_view: str = ""
    markets_vol_view: str = ""
    narrative_citations: list[NewsCitation] = Field(default_factory=list)
    data_sources: list[str] = Field(default_factory=list)
    fundamentals_notes: list[str] = Field(
        default_factory=list,
        description="Structured price/valuation/revision highlights (yfinance, optional Finnhub)",
    )
    themes: list[FinalTheme]
    regime_themes: list[AgentTheme] = Field(default_factory=list)
    narrative_themes: list[AgentTheme] = Field(default_factory=list)
    markets_themes: list[AgentTheme] = Field(default_factory=list)
    disclaimer: str = (
        "For research purposes only. Not investment advice. "
        "Make your own decisions based on your risk tolerance."
    )
