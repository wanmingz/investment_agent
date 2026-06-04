from datetime import date

from investment_agent.config import Settings
from investment_agent.dates import format_date_display, format_date_iso
from investment_agent.llm import LLMClient
from investment_agent.market_data import VolSnapshot
from investment_agent.models import EquityReport, MacroReport, QuantReport

SYSTEM = """You are Agent 3: a quantitative analyst specializing in volatility and risk regimes.

Your job: assess investable THEMES through volatility, correlation, and positioning risk.

Write ALL output in English only.

Stage classification from QUANT / vol lens (use all five when appropriate):
- early: vol compressed or declining from elevated levels, positive momentum with low realized vol
- early_mid: vol picking up from low base, momentum strengthening, options still reasonably priced
- mid: vol normalizing upward, trend strong but drawdowns increasing, vol risk premium building
- mid_late: elevated but stable vol, correlation rising within theme, skew starting to price tail risk
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
        *,
        as_of: date | None = None,
    ) -> QuantReport:
        as_of = as_of or date.today()
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

        user = f"""Analysis as-of date: {format_date_display(as_of)} ({format_date_iso(as_of)}).
Use this as "today" — do not use any other date.
Respond in English only.

Region: {self._region}

Prior agent outputs:
{json.dumps(context, indent=2, ensure_ascii=False)}

Live vol data block:
{vol.to_prompt_block()}

Produce 4-6 themes with quant/vol-based stage (early/early_mid/mid/mid_late/late).
Set vix_proxy_level from live data if provided."""
        return self._llm.structured(system=SYSTEM, user=user, schema=QuantReport)
