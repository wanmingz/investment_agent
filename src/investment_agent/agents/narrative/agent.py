from investment_agent.dates import format_date_display, format_date_iso
from investment_agent.agents.narrative.input import NarrativeInput
from investment_agent.llm import LLMClient
from investment_agent.models import NarrativeReport, NewsCitation

SYSTEM = """You are the Narrative analyst: financial news analyst using retrieved articles only (RAG).

Write ALL output in English only.

Rules:
- Base backdrop, signals, drivers, and risks ONLY on provided articles.
- key_drivers_sourced and risks_sourced MUST use citation_ids from the context.
- Produce 3-4 themes from HEADLINES ONLY (news flow lens: early/early_mid/mid/mid_late/late).
- citations: return only articles you cite in drivers/risks (ids must match context); others are backfilled.
- Keep thesis and drivers concise."""


class NarrativeAgent:
    def __init__(self, llm: LLMClient):
        self._llm = llm

    def analyze(self, inp: NarrativeInput) -> NarrativeReport:
        notes = ", ".join(inp.ingest_notes[:3]) if inp.ingest_notes else "none"
        user = f"""As-of: {format_date_display(inp.as_of)} ({format_date_iso(inp.as_of)}). Region: {inp.region}.
Corpus: {inp.articles_in_corpus} articles | Retrieved: {inp.articles_retrieved}. Ingest: {notes}.

{inp.context_block}

Set articles_retrieved to {inp.articles_retrieved}.
Return 3-4 English themes grounded in the articles above."""

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
