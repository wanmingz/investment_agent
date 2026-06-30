from investment_agent.dates import format_date_display, format_date_iso
from investment_agent.data_plane import MarketsInput
from investment_agent.llm import LLMClient
from investment_agent.models import MarketsReport

SYSTEM = """You are the Markets analyst combining fundamentals and volatility/risk lenses.

Your job in ONE response:
1) Fundamentals lens: 3-5 themes from fundamentals and market structure.
2) Vol lens: 3-5 themes from the live volatility block.

Write ALL output in English only.

Work INDEPENDENTLY — do not assume themes from other agents exist.
Fundamentals theme names should reflect sectors, styles, or clusters (e.g. "Software margin recovery").
Vol theme names should reflect risk/regime angles (e.g. "Low-vol carry in large-cap tech").

Fundamentals stage lens:
- early / early_mid / mid / mid_late / late (valuation, revisions, crowding)

Vol stage lens:
- early / early_mid / mid / mid_late / late (vol compression, expansion, crisis)

Use ONLY numbers in the structured fundamentals block for valuation claims.
Weight the volatility block heavily for vol themes and vol_regime.

Output valid JSON:
{
  "market_style": "growth/value, cap bias, sector leadership",
  "vol_regime": "low" | "normal" | "elevated" | "crisis",
  "vix_proxy_level": number or null,
  "fundamentals_view": "1 paragraph fundamentals narrative",
  "vol_view": "1 paragraph vol/risk narrative",
  "fundamentals_themes": [ AgentTheme — 3-5 fundamentals themes ],
  "vol_themes": [ AgentTheme — 3-5 vol/risk themes ],
  "valuation_notes": ["notes citing structured metrics"],
  "vol_signals": ["signal1", "signal2"]
}"""


class MarketsAgent:
    def __init__(self, llm: LLMClient):
        self._llm = llm

    def analyze(self, inp: MarketsInput) -> MarketsReport:
        fund_block = inp.fundamentals.to_prompt_block()
        vol_block = inp.vol.to_prompt_block()

        user = f"""Analysis as-of date: {format_date_display(inp.as_of)} ({format_date_iso(inp.as_of)}).
Use this as "today" — do not use any other date.
Respond in English only.

Region: {inp.region}

{fund_block}

{vol_block}

Produce fundamentals_themes and vol_themes with distinct names.
Set vix_proxy_level from live vol data if provided.
Write fundamentals_view and vol_view as separate paragraphs."""
        return self._llm.structured(system=SYSTEM, user=user, schema=MarketsReport)
