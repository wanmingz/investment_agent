from investment_agent.dates import format_date_display, format_date_iso
from investment_agent.data_plane import NarrativeInput
from investment_agent.llm import LLMClient
from investment_agent.models import NarrativeReport, NewsCitation

SYSTEM = """You are the Narrative analyst: a financial news analyst using retrieved articles only (RAG).

Write ALL output in English only.

You receive a block of news articles with IDs like [fh-...] or [tt-...].
Rules:
- Base narrative_backdrop, signals, drivers, and risks ONLY on provided articles.
- key_drivers_sourced and risks_sourced MUST cite citation_ids that exist in the context.
- Do NOT invent URLs or headlines not in the context.
- Produce 3-6 themes in "themes" derived FROM HEADLINES ONLY — do not reuse a generic macro theme checklist.
- Each theme in "themes" must reflect narrative heat in the news (mergers, policy shocks, sector moves, etc.).
- For each theme, include stage from a NEWS flow lens (early, early_mid, mid, mid_late, late).
- If evidence is thin, use fewer themes and note limitations in narrative_backdrop.

Output valid JSON:
{
  "narrative_backdrop": "2-3 sentences from recent headlines",
  "narrative_sentiment": "risk-on" | "neutral" | "risk-off",
  "retrieval_query": "query used",
  "articles_retrieved": number,
  "ingest_notes": ["provider notes"],
  "citations": [
    {"id": "...", "title": "...", "source": "...", "url": "...", "published_at": "..."}
  ],
  "narrative_signals": ["signal with [id] reference where possible"],
  "key_drivers_sourced": [{"text": "...", "citation_ids": ["id1"]}],
  "risks_sourced": [{"text": "...", "citation_ids": ["id1"]}],
  "themes": [ AgentTheme — required 3-6 news-driven themes with name, thesis, stage, etc. ]
}"""


class NarrativeAgent:
    def __init__(self, llm: LLMClient):
        self._llm = llm

    def analyze(self, inp: NarrativeInput) -> NarrativeReport:
        user = f"""Analysis as-of date: {format_date_display(inp.as_of)} ({format_date_iso(inp.as_of)}).
Respond in English only.
Region: {inp.region}

You are independent from other agents — do NOT assume any pre-defined macro theme list.

Retrieval query: {inp.retrieval_query}
Articles in corpus: {inp.articles_in_corpus} | Retrieved for context: {inp.articles_retrieved}
Ingest notes: {inp.ingest_notes}

{inp.context_block}

Set articles_retrieved to {inp.articles_retrieved}.
Include citations for every article in the retrieved context block.
Produce key_drivers_sourced and risks_sourced with valid citation_ids.
Return 3-6 themes in "themes" grounded in the articles above."""

        report = self._llm.structured(system=SYSTEM, user=user, schema=NarrativeReport)
        retrieved = list(inp.retrieved)

        if retrieved and len(report.citations) < len(retrieved):
            existing = {c.id for c in report.citations}
            extra = [
                NewsCitation(
                    id=a.id,
                    title=a.title,
                    source=a.source,
                    url=a.url,
                    published_at=a.published_at,
                )
                for a in retrieved
                if a.id not in existing
            ]
            report = report.model_copy(
                update={
                    "citations": report.citations + extra,
                    "retrieval_query": inp.retrieval_query,
                    "articles_retrieved": inp.articles_retrieved,
                    "ingest_notes": list(inp.ingest_notes),
                }
            )
        else:
            report = report.model_copy(
                update={
                    "retrieval_query": inp.retrieval_query,
                    "articles_retrieved": inp.articles_retrieved,
                    "ingest_notes": list(inp.ingest_notes),
                }
            )
        return report
