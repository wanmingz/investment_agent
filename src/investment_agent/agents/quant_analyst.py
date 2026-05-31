from investment_agent.config import Settings
from investment_agent.llm import LLMClient
from investment_agent.market_data import VolSnapshot
from investment_agent.models import EquityReport, MacroReport, QuantReport

SYSTEM = """You are Agent 3: a quantitative analyst specializing in volatility and risk regimes.

Your job: assess investable THEMES through volatility, correlation, and positioning risk.

Stage classification from QUANT / vol lens:
- early: vol compressed or declining from elevated levels, positive momentum with low realized vol, options not expensive
- mid: vol normalizing upward, trend strong but drawdowns increasing, vol risk premium building
- late: vol spike or persistently elevated, correlation breakdown risk, skew expensive, mean-reversion signals

You receive live volatility data when available — weight it heavily for stage calls.

Output valid JSON:
{
  "vol_regime": "low" | "normal" | "elevated" | "crisis",
  "vix_proxy_level": number or null,
  "themes": [ AgentTheme structure ],
  "vol_signals": ["signal1", "signal2"]
}"""


class QuantAnalyst:
    def __init__(self, llm: LLMClient, settings: Settings):
        self._llm = llm
        self._region = settings.market_region

    def analyze(
        self,
        macro: MacroReport,
        equity: EquityReport,
        vol: VolSnapshot,
    ) -> QuantReport:
        context = {
            "macro": macro.model_dump(),
            "equity": equity.model_dump(),
            "vol_snapshot": {
                "vix": vol.vix_level,
                "vix_20d_change_pct": vol.vix_20d_change_pct,
                "sector_vol": vol.sector_vol,
            },
        }
        import json

        user = f"""Region: {self._region}

Prior agent outputs:
{json.dumps(context, indent=2, ensure_ascii=False)}

Live vol data block:
{vol.to_prompt_block()}

Produce 4-6 themes with quant/vol-based stage (early/mid/late).
Set vix_proxy_level from live data if provided."""
        return self._llm.structured(system=SYSTEM, user=user, schema=QuantReport)
