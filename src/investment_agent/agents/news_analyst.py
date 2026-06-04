from datetime import date

from investment_agent.config import Settings
from investment_agent.dates import format_date_display, format_date_iso
from investment_agent.llm import LLMClient
from investment_agent.models import MacroReport, NewsReport
from investment_agent.news.ingest import fetch_news_articles
from investment_agent.news.rag import (
    build_retrieval_query,
    format_context_block,
    retrieve_articles,
)

SYSTEM = """You are Agent 4: a financial news analyst using retrieved articles only (RAG).

Write ALL output in English only.

You receive a block of news articles with IDs like [fh-...] or [tt-...].
Rules:
- Base news_backdrop, signals, drivers, and risks ONLY on provided articles.
- key_drivers_sourced and risks_sourced MUST cite citation_ids that exist in the context.
- Do NOT invent URLs or headlines not in the context.
- If evidence is thin, say so and use fewer sourced items.
- Stage themes from a NEWS flow / narrative heat lens (five stages: early, early_mid, mid, mid_late, late).

Output valid JSON:
{
  "news_backdrop": "2-3 sentences from recent headlines",
  "narrative_sentiment": "risk-on" | "neutral" | "risk-off",
  "retrieval_query": "query used",
  "articles_retrieved": number,
  "ingest_notes": ["provider notes"],
  "citations": [
    {"id": "...", "title": "...", "source": "...", "url": "...", "published_at": "..."}
  ],
  "news_signals": ["signal with [id] reference where possible"],
  "key_drivers_sourced": [{"text": "...", "citation_ids": ["id1"]}],
  "risks_sourced": [{"text": "...", "citation_ids": ["id1"]}],
  "themes": [ AgentTheme structure — optional 3-5 news-driven themes ]
}"""


class NewsAnalyst:
    def __init__(self, llm: LLMClient, settings: Settings):
        self._llm = llm
        self._settings = settings

    def analyze(self, macro: MacroReport, *, as_of: date | None = None) -> NewsReport:
        as_of = as_of or date.today()
        theme_names = [t.name for t in macro.themes]
        query = build_retrieval_query(
            region=self._settings.market_region,
            theme_names=theme_names,
            macro_backdrop=macro.macro_backdrop,
        )

        articles, ingest_notes = fetch_news_articles(
            region=self._settings.market_region,
            finnhub_key=self._settings.finnhub_api_key,
            max_articles=self._settings.news_max_articles,
        )
        retrieved = retrieve_articles(articles, query, top_k=self._settings.rag_top_k)
        context = format_context_block(retrieved)

        user = f"""Analysis as-of date: {format_date_display(as_of)} ({format_date_iso(as_of)}).
Respond in English only.
Region: {self._settings.market_region}

Retrieval query: {query}
Articles in corpus: {len(articles)} | Retrieved for context: {len(retrieved)}
Ingest notes: {ingest_notes}

Macro context (for thematic alignment only — news claims must cite articles below):
{macro.model_dump_json(indent=2)}

{context}

Set articles_retrieved to {len(retrieved)}.
Include citations for every article in the retrieved context block.
Produce key_drivers_sourced and risks_sourced with valid citation_ids."""

        report = self._llm.structured(system=SYSTEM, user=user, schema=NewsReport)

        # Ensure citations cover retrieved articles when LLM omits them
        if retrieved and len(report.citations) < len(retrieved):
            existing = {c.id for c in report.citations}
            from investment_agent.models import NewsCitation

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
                    "retrieval_query": query,
                    "articles_retrieved": len(retrieved),
                    "ingest_notes": ingest_notes,
                }
            )
        else:
            report = report.model_copy(
                update={
                    "retrieval_query": query,
                    "articles_retrieved": len(retrieved),
                    "ingest_notes": ingest_notes,
                }
            )
        return report
