from pathlib import Path

from investment_agent.models import InvestmentBrief

DEFAULT_REPORT_PATH = Path(__file__).resolve().parents[2] / "reports" / "latest.json"


def save_brief(brief: InvestmentBrief, path: Path | None = None) -> Path:
    target = path or DEFAULT_REPORT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(brief.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def load_brief(path: Path | None = None) -> InvestmentBrief | None:
    target = path or DEFAULT_REPORT_PATH
    if not target.is_file():
        return None
    return InvestmentBrief.model_validate_json(target.read_text(encoding="utf-8"))
