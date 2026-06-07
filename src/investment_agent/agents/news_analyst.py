from datetime import date

from investment_agent.config import Settings
from investment_agent.dates import format_date_display, format_date_iso
from investment_agent.llm import LLMClient
from investment_agent.models import NewsReport
from investment_agent.news.ingest import fetch_news_articles
from investment_agent.news.rag import (
    build_news_retrieval_query,
    format_context_block,
    retrieve_articles,
)

SYSTEM = """You are Agent 2: a financial news analyst using retrieved articles only (RAG).

Write ALL output in English only.

You receive a block of news articles with IDs like [fh-...] or [tt-...].
Rules:
- Base news_backdrop, signals, drivers, and risks ONLY on provided articles.
- key_drivers_sourced and risks_sourced MUST cite citation_ids that exist in the context.
- Do NOT invent URLs or headlines not in the context.
- Produce 3-6 themes in "themes" derived FROM HEADLINES ONLY — do not reuse a generic macro theme checklist.
- Each theme in "themes" must reflect narrative heat in the news (mergers, policy shocks, sector moves, etc.).
- For each theme, include stage from a NEWS flow lens (early, early_mid, mid, mid_late, late).
- If evidence is thin, use fewer themes and say so in ingest_notes via your reasoning in news_backdrop.

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
  "themes": [ AgentTheme — required 3-6 news-driven themes with name, thesis, stage, etc. ]
}"""


class NewsAnalyst:
    def __init__(self, llm: LLMClient, settings: Settings):
        self._llm = llm
        self._settings = settings

    def analyze(self, *, as_of: date | None = None) -> NewsReport:
        as_of = as_of or date.today()
        query = build_news_retrieval_query(region=self._settings.market_region)

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

You are independent from other agents — do NOT assume any pre-defined macro theme list.

Retrieval query: {query}
Articles in corpus: {len(articles)} | Retrieved for context: {len(retrieved)}
Ingest notes: {ingest_notes}

{context}

Set articles_retrieved to {len(retrieved)}.
Include citations for every article in the retrieved context block.
Produce key_drivers_sourced and risks_sourced with valid citation_ids.
Return 3-6 themes in "themes" grounded in the articles above."""

        report = self._llm.structured(system=SYSTEM, user=user, schema=NewsReport)

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
