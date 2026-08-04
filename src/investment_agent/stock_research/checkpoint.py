"""Checkpoint / resume for stock research (isolated from theme pipeline)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from investment_agent.stock_research.bundle import StockBundle
from investment_agent.stock_research.models import (
    BusinessReport,
    ExpectationReport,
    FinancialReport,
    ValuationReport,
)

T = TypeVar("T", bound=BaseModel)

CACHE_ROOT = Path(__file__).resolve().parents[3] / "reports" / "cache" / "stock_research"
PIPELINE_VERSION = 1
META_FILE = "run_meta.json"


def is_resume_enabled() -> bool:
    import os

    return os.getenv("RESUME_CHECKPOINT", "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def cache_dir(ticker: str) -> Path:
    path = CACHE_ROOT / ticker.strip().upper()
    path.mkdir(parents=True, exist_ok=True)
    return path


def clear_checkpoint(ticker: str) -> None:
    d = CACHE_ROOT / ticker.strip().upper()
    if not d.is_dir():
        return
    for p in d.iterdir():
        if p.is_file():
            p.unlink()


def list_checkpoint_steps(ticker: str) -> list[str]:
    d = CACHE_ROOT / ticker.strip().upper()
    if not d.is_dir():
        return []
    names = []
    for key in ("bundle", "business", "financial", "valuation", "expectation"):
        if (d / f"{key}.json").is_file():
            names.append(key)
    return names


def save_run_meta(*, ticker: str, as_of: date) -> None:
    cache_dir(ticker).joinpath(META_FILE).write_text(
        json.dumps(
            {
                "ticker": ticker.strip().upper(),
                "as_of": as_of.isoformat(),
                "pipeline_version": PIPELINE_VERSION,
            }
        ),
        encoding="utf-8",
    )


def meta_matches(*, ticker: str, as_of: date) -> bool:
    path = CACHE_ROOT / ticker.strip().upper() / META_FILE
    if not path.is_file():
        return False
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return (
        meta.get("ticker") == ticker.strip().upper()
        and meta.get("as_of") == as_of.isoformat()
        and meta.get("pipeline_version") == PIPELINE_VERSION
    )


def save_model(ticker: str, name: str, model: BaseModel) -> None:
    cache_dir(ticker).joinpath(f"{name}.json").write_text(
        model.model_dump_json(indent=2),
        encoding="utf-8",
    )


def load_model(ticker: str, name: str, schema: type[T]) -> T | None:
    path = CACHE_ROOT / ticker.strip().upper() / f"{name}.json"
    if not path.is_file():
        return None
    try:
        return schema.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def save_bundle(bundle: StockBundle) -> None:
    payload = {
        "ticker": bundle.ticker,
        "as_of": bundle.as_of.isoformat(),
        "company_name": bundle.company_name,
        "last_price": bundle.last_price,
        "business_block": bundle.business_block,
        "financial_block": bundle.financial_block,
        "valuation_block": bundle.valuation_block,
        "expectation_block": bundle.expectation_block,
        "notes": list(bundle.notes),
    }
    cache_dir(bundle.ticker).joinpath("bundle.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_bundle(ticker: str) -> StockBundle | None:
    path = CACHE_ROOT / ticker.strip().upper() / "bundle.json"
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return StockBundle(
            ticker=raw["ticker"],
            as_of=date.fromisoformat(raw["as_of"]),
            company_name=raw.get("company_name") or raw["ticker"],
            last_price=raw.get("last_price"),
            business_block=raw.get("business_block") or "",
            financial_block=raw.get("financial_block") or "",
            valuation_block=raw.get("valuation_block") or "",
            expectation_block=raw.get("expectation_block") or "",
            notes=list(raw.get("notes") or []),
        )
    except Exception:  # noqa: BLE001
        return None


def save_business(ticker: str, r: BusinessReport) -> None:
    save_model(ticker, "business", r)


def load_business(ticker: str) -> BusinessReport | None:
    return load_model(ticker, "business", BusinessReport)


def save_financial(ticker: str, r: FinancialReport) -> None:
    save_model(ticker, "financial", r)


def load_financial(ticker: str) -> FinancialReport | None:
    return load_model(ticker, "financial", FinancialReport)


def save_valuation(ticker: str, r: ValuationReport) -> None:
    save_model(ticker, "valuation", r)


def load_valuation(ticker: str) -> ValuationReport | None:
    return load_model(ticker, "valuation", ValuationReport)


def save_expectation(ticker: str, r: ExpectationReport) -> None:
    save_model(ticker, "expectation", r)


def load_expectation(ticker: str) -> ExpectationReport | None:
    return load_model(ticker, "expectation", ExpectationReport)
