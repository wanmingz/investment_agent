"""Persist InvestmentBrief + safe accessors for schema versions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from investment_agent.dates import analysis_date, build_as_of_context, format_date_iso
from investment_agent.models import FinalTheme, InvestmentBrief, NewsCitation, SourcedItem

DEFAULT_REPORT_PATH = Path(__file__).resolve().parents[2] / "reports" / "latest.json"


def _get(obj: Any, name: str, default: Any = None) -> Any:
    return getattr(obj, name, default)


def brief_news_view(brief: InvestmentBrief) -> str:
    return _get(brief, "news_view", "") or ""


def brief_data_sources(brief: InvestmentBrief) -> list[str]:
    val = _get(brief, "data_sources", None)
    return list(val) if val else []


def brief_agent_themes(brief: InvestmentBrief, agent: str) -> list:
    key = f"{agent}_themes"
    val = _get(brief, key, None)
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
    data.setdefault("macro_themes", [])
    data.setdefault("news_themes", [])
    data.setdefault("equity_themes", [])
    data.setdefault("quant_themes", [])
    for theme in data.get("themes", []):
        if isinstance(theme, dict):
            theme.setdefault("key_drivers_sourced", [])
            theme.setdefault("risks_sourced", [])
            theme.setdefault("contributing_agents", [])
            theme.setdefault("primary_agent", "")
            theme.setdefault("agent_stages", {})
    return data


def save_brief(brief: InvestmentBrief, path: Path | None = None) -> Path:
    target = path or DEFAULT_REPORT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        brief.model_dump_json(indent=2, ensure_ascii=False, by_alias=True),
        encoding="utf-8",
    )
    return target


def load_brief(path: Path | None = None) -> InvestmentBrief | None:
    target = path or DEFAULT_REPORT_PATH
    if not target.is_file():
        return None
    raw = json.loads(target.read_text(encoding="utf-8"))
    brief = InvestmentBrief.model_validate(migrate_brief_dict(raw))
    return _normalize_loaded_brief(brief)


def _as_of_prefixed(ctx: str) -> bool:
    c = ctx.strip().lower()
    return c.startswith("as of") or ctx.strip().startswith("截至")


def _normalize_loaded_brief(brief: InvestmentBrief) -> InvestmentBrief:
    """Backfill date fields for older reports."""
    updates: dict = {}
    if not brief.report_date:
        updates["report_date"] = format_date_iso(analysis_date())
    if not _as_of_prefixed(brief.as_of_context):
        as_of = analysis_date()
        if brief.report_date:
            from datetime import date as date_cls

            try:
                as_of = date_cls.fromisoformat(brief.report_date)
            except ValueError:
                pass
        updates["as_of_context"] = build_as_of_context(brief.as_of_context, as_of=as_of)
    if not updates:
        return brief
    return brief.model_copy(update=updates)
