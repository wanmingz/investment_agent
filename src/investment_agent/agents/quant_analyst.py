from datetime import date

from investment_agent.config import Settings
from investment_agent.dates import format_date_display, format_date_iso
from investment_agent.llm import LLMClient
from investment_agent.market_data import VolSnapshot
from investment_agent.models import QuantReport

SYSTEM = """You are Agent 4: a quantitative analyst specializing in volatility and risk regimes.

Your job: identify 3-6 investable THEMES from vol, momentum, and correlation data only.

Write ALL output in English only.

You work INDEPENDENTLY — do not copy theme names from macro, news, or equity agents.
Name themes by risk/regime angle (e.g. "Low-vol carry in large-cap tech", "Energy vol breakout").

Stage classification from QUANT / vol lens (use all five when appropriate):
- early: vol compressed or declining from elevated levels, positive momentum with low realized vol
- early_mid: vol picking up from low base, momentum strengthening, options still reasonably priced
- mid: vol normalizing upward, trend strong but drawdowns increasing, vol risk premium building
- mid_late: elevated but stable vol, correlation rising within theme, skew starting to price tail risk
- late: vol spike or persistently elevated, correlation breakdown risk, skew expensive, mean-reversion signals

Weight the live volatility block heavily for stage calls.

Output valid JSON:
{
  "vol_regime": "low" | "normal" | "elevated" | "crisis",
  "vix_proxy_level": number or null,
  "themes": [ AgentTheme structure — 3-6 quant/vol themes ],
  "vol_signals": ["signal1", "signal2"]
}"""


class QuantAnalyst:
    def __init__(self, llm: LLMClient, settings: Settings):
        self._llm = llm
        self._region = settings.market_region

    def analyze(
        self,
        vol: VolSnapshot,
        *,
        dominant_regime: str = "",
        as_of: date | None = None,
    ) -> QuantReport:
        as_of = as_of or date.today()
        regime_hint = (
            f"Optional macro regime hint (do not copy as theme names): {dominant_regime}"
            if dominant_regime
            else "No macro regime hint provided."
        )
        user = f"""Analysis as-of date: {format_date_display(as_of)} ({format_date_iso(as_of)}).
Use this as "today" — do not use any other date.
Respond in English only.

Region: {self._region}

{regime_hint}

Live vol data block:
{vol.to_prompt_block()}

Produce 3-6 themes with quant/vol-based names and stages (early/early_mid/mid/mid_late/late).
Set vix_proxy_level from live data if provided."""
        return self._llm.structured(system=SYSTEM, user=user, schema=QuantReport)
