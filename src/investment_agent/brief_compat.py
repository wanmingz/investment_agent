"""Safe accessors for InvestmentBrief / FinalTheme across schema versions."""

from __future__ import annotations

from typing import Any

from investment_agent.models import FinalTheme, InvestmentBrief, NewsCitation, SourcedItem


def _get(obj: Any, name: str, default: Any = None) -> Any:
    return getattr(obj, name, default)


def brief_news_view(brief: InvestmentBrief) -> str:
    return _get(brief, "news_view", "") or ""


def brief_data_sources(brief: InvestmentBrief) -> list[str]:
    val = _get(brief, "data_sources", None)
    return list(val) if val else []


def brief_fundamentals_notes(brief: InvestmentBrief) -> list[str]:
    val = _get(brief, "fundamentals_notes", None)
    return list(val) if val else []


def brief_news_citations(brief: InvestmentBrief) -> list[NewsCitation]:
    val = _get(brief, "news_citations", None)
    return list(val) if val else []


def theme_drivers_sourced(theme: FinalTheme) -> list[SourcedItem]:
    val = _get(theme, "key_drivers_sourced", None)
    return list(val) if val else []


def theme_risks_sourced(theme: FinalTheme) -> list[SourcedItem]:
    val = _get(theme, "risks_sourced", None)
    return list(val) if val else []


def migrate_brief_dict(data: dict) -> dict:
    """Fill missing keys when loading older reports/latest.json."""
    data.setdefault("news_view", "")
    data.setdefault("news_citations", [])
    data.setdefault("data_sources", [])
    data.setdefault("fundamentals_notes", [])
    for theme in data.get("themes", []):
        if isinstance(theme, dict):
            theme.setdefault("key_drivers_sourced", [])
            theme.setdefault("risks_sourced", [])
    return data
