from datetime import date, datetime

__all__ = [
    "analysis_date",
    "format_date_display",
    "format_date_zh",
    "format_date_iso",
    "format_datetime_display",
    "as_of_context_prefix",
    "build_as_of_context",
]


def analysis_date() -> date:
    """Local calendar date for the analysis run."""
    return date.today()


def format_date_display(d: date | None = None) -> str:
    d = d or analysis_date()
    return d.strftime("%B %d, %Y")


format_date_zh = format_date_display


def format_date_iso(d: date | None = None) -> str:
    return (d or analysis_date()).isoformat()


def format_datetime_display(d: date | None = None) -> str:
    d = d or analysis_date()
    now = datetime.now().astimezone()
    return f"{format_date_display(d)} {now.strftime('%H:%M')}"


def as_of_context_prefix(d: date | None = None, region: str = "global") -> str:
    d = d or analysis_date()
    base = f"As of {format_date_display(d)} ({format_date_iso(d)})"
    if region and region.lower() != "global":
        return f"{base} · {region} market"
    return base


def build_as_of_context(
    llm_context: str,
    *,
    as_of: date | None = None,
    region: str = "global",
) -> str:
    """Ensure report header always uses the analysis run date."""
    prefix = as_of_context_prefix(as_of, region)
    note = (llm_context or "").strip()
    if note.lower().startswith("as of"):
        if "·" in note:
            note = note.split("·", 1)[1].strip()
        else:
            note = ""
    if note.startswith("截至"):
        if "·" in note:
            note = note.split("·", 1)[1].strip()
        else:
            note = ""
    if note:
        return f"{prefix} · {note}"
    return prefix
