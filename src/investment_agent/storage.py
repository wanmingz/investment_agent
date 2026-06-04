import json
from pathlib import Path

from investment_agent.brief_compat import migrate_brief_dict
from investment_agent.dates import analysis_date, build_as_of_context, format_date_iso
from investment_agent.models import InvestmentBrief

DEFAULT_REPORT_PATH = Path(__file__).resolve().parents[2] / "reports" / "latest.json"


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
