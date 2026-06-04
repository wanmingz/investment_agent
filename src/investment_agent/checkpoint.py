"""Save partial agent outputs so a failed run can resume without redoing LLM calls."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from investment_agent.data.snapshot import FundamentalsSnapshot, SymbolFundamentals
from investment_agent.data.price import PriceMetrics
from investment_agent.data.revisions import RevisionMetrics
from investment_agent.data.valuation import ValuationMetrics
from investment_agent.models import EquityReport, MacroReport, NewsReport, QuantReport

T = TypeVar("T", bound=BaseModel)

CACHE_DIR = Path(__file__).resolve().parents[2] / "reports" / "cache"
META_FILE = "run_meta.json"


def is_resume_enabled() -> bool:
    import os

    return os.getenv("RESUME_CHECKPOINT", "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def cache_dir() -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR


def save_run_meta(*, as_of: date, region: str) -> None:
    cache_dir().joinpath(META_FILE).write_text(
        json.dumps({"as_of": as_of.isoformat(), "region": region}),
        encoding="utf-8",
    )


def load_run_meta() -> dict | None:
    path = cache_dir() / META_FILE
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def meta_matches(*, as_of: date, region: str) -> bool:
    meta = load_run_meta()
    if not meta:
        return False
    return meta.get("as_of") == as_of.isoformat() and meta.get("region") == region


def _model_path(name: str) -> Path:
    return cache_dir() / f"{name}.json"


def save_model(name: str, model: BaseModel) -> None:
    _model_path(name).write_text(
        model.model_dump_json(indent=2),
        encoding="utf-8",
    )


def load_model(name: str, schema: type[T]) -> T | None:
    path = _model_path(name)
    if not path.is_file():
        return None
    try:
        return schema.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _row_from_dict(d: dict) -> SymbolFundamentals:
    return SymbolFundamentals(
        label=d["label"],
        symbol=d["symbol"],
        price=PriceMetrics(**d["price"]),
        valuation=ValuationMetrics(**d["valuation"]),
        revision=RevisionMetrics(**d["revision"]) if d.get("revision") else None,
    )


def save_fundamentals(snapshot: FundamentalsSnapshot) -> None:
    cache_dir().joinpath("fundamentals.json").write_text(
        json.dumps(asdict(snapshot), indent=2),
        encoding="utf-8",
    )


def load_fundamentals() -> FundamentalsSnapshot | None:
    path = cache_dir() / "fundamentals.json"
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        rows = [_row_from_dict(r) for r in raw.get("rows", [])]
        return FundamentalsSnapshot(
            as_of=raw.get("as_of", ""),
            rows=rows,
            signals=list(raw.get("signals", [])),
            notes=list(raw.get("notes", [])),
        )
    except Exception:
        return None


def list_checkpoint_steps() -> list[str]:
    steps = []
    for name in ("macro", "news", "fundamentals", "equity", "quant"):
        if name == "fundamentals":
            if (cache_dir() / "fundamentals.json").is_file():
                steps.append(name)
        elif _model_path(name).is_file():
            steps.append(name)
    return steps


def clear_checkpoint() -> None:
    if not cache_dir().exists():
        return
    for p in cache_dir().glob("*.json"):
        p.unlink(missing_ok=True)


def save_macro(m: MacroReport) -> None:
    save_model("macro", m)


def load_macro() -> MacroReport | None:
    return load_model("macro", MacroReport)


def save_news(n: NewsReport) -> None:
    save_model("news", n)


def load_news() -> NewsReport | None:
    return load_model("news", NewsReport)


def save_equity(e: EquityReport) -> None:
    save_model("equity", e)


def load_equity() -> EquityReport | None:
    return load_model("equity", EquityReport)


def save_quant(q: QuantReport) -> None:
    save_model("quant", q)


def load_quant() -> QuantReport | None:
    return load_model("quant", QuantReport)
