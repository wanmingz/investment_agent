"""Save partial v2 pipeline outputs for resume without redoing LLM calls."""

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
from investment_agent.data_plane import (
    DataPlaneSnapshot,
    MarketsInput,
    NarrativeInput,
    RegimeInput,
)
from investment_agent.data.snapshot import VolSnapshot
from investment_agent.models import MarketsReport, NarrativeReport, RegimeReport
from investment_agent.news.ingest import NewsArticle

T = TypeVar("T", bound=BaseModel)

CACHE_DIR = Path(__file__).resolve().parents[2] / "reports" / "cache"
META_FILE = "run_meta.json"
PIPELINE_VERSION = 3


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
        json.dumps(
            {
                "as_of": as_of.isoformat(),
                "region": region,
                "pipeline_version": PIPELINE_VERSION,
            }
        ),
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
    if meta.get("pipeline_version") != PIPELINE_VERSION:
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


def _fundamentals_to_dict(snapshot: FundamentalsSnapshot) -> dict:
    return asdict(snapshot)


def _fundamentals_from_dict(raw: dict) -> FundamentalsSnapshot:
    rows = [_row_from_dict(r) for r in raw.get("rows", [])]
    return FundamentalsSnapshot(
        as_of=raw.get("as_of", ""),
        rows=rows,
        signals=list(raw.get("signals", [])),
        notes=list(raw.get("notes", [])),
    )


def _article_to_dict(a: NewsArticle) -> dict:
    return {
        "id": a.id,
        "title": a.title,
        "summary": a.summary,
        "url": a.url,
        "source": a.source,
        "published_at": a.published_at,
        "provider": a.provider,
    }


def _article_from_dict(d: dict) -> NewsArticle:
    return NewsArticle(
        id=d["id"],
        title=d["title"],
        summary=d.get("summary", ""),
        url=d.get("url", ""),
        source=d.get("source", ""),
        published_at=d.get("published_at", ""),
        provider=d.get("provider", ""),
    )


def save_data_plane(plane: DataPlaneSnapshot) -> None:
    ni = plane.narrative_input
    mi = plane.markets_input
    payload = {
        "as_of": plane.as_of.isoformat(),
        "region": plane.region,
        "data_plane_notes": plane.data_plane_notes,
        "regime_input": {
            "as_of": plane.regime_input.as_of.isoformat(),
            "region": plane.regime_input.region,
            "macro_context_block": plane.regime_input.macro_context_block,
            "context_notes": list(plane.regime_input.context_notes),
        },
        "narrative_input": {
            "as_of": ni.as_of.isoformat(),
            "region": ni.region,
            "retrieval_query": ni.retrieval_query,
            "articles_in_corpus": ni.articles_in_corpus,
            "articles_retrieved": ni.articles_retrieved,
            "ingest_notes": ni.ingest_notes,
            "context_block": ni.context_block,
            "retrieved": [_article_to_dict(a) for a in ni.retrieved],
        },
        "markets_input": {
            "as_of": mi.as_of.isoformat(),
            "region": mi.region,
            "fundamentals": _fundamentals_to_dict(mi.fundamentals),
            "vol": asdict(mi.vol),
        },
    }
    cache_dir().joinpath("data_plane.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def load_data_plane() -> DataPlaneSnapshot | None:
    path = cache_dir() / "data_plane.json"
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        ni = raw["narrative_input"]
        mi = raw["markets_input"]
        retrieved = tuple(_article_from_dict(a) for a in ni.get("retrieved", []))
        as_of = date.fromisoformat(raw["as_of"])
        ri = raw["regime_input"]
        regime_input = RegimeInput(
            as_of=date.fromisoformat(ri["as_of"]),
            region=ri["region"],
            macro_context_block=ri.get("macro_context_block", ""),
            context_notes=tuple(ri.get("context_notes", [])),
        )
        narrative_input = NarrativeInput(
            as_of=date.fromisoformat(ni["as_of"]),
            region=ni["region"],
            retrieval_query=ni["retrieval_query"],
            articles_in_corpus=ni["articles_in_corpus"],
            articles_retrieved=ni["articles_retrieved"],
            ingest_notes=list(ni.get("ingest_notes", [])),
            context_block=ni["context_block"],
            retrieved=retrieved,
        )
        vol_raw = mi["vol"]
        markets_input = MarketsInput(
            as_of=date.fromisoformat(mi["as_of"]),
            region=mi["region"],
            fundamentals=_fundamentals_from_dict(mi["fundamentals"]),
            vol=VolSnapshot(
                vix_level=vol_raw.get("vix_level"),
                vix_20d_change_pct=vol_raw.get("vix_20d_change_pct"),
                sector_vol=dict(vol_raw.get("sector_vol", {})),
                notes=list(vol_raw.get("notes", [])),
            ),
        )
        return DataPlaneSnapshot(
            as_of=as_of,
            region=raw["region"],
            regime_input=regime_input,
            narrative_input=narrative_input,
            markets_input=markets_input,
            data_plane_notes=list(raw.get("data_plane_notes", [])),
        )
    except Exception:
        return None


def list_checkpoint_steps() -> list[str]:
    steps = []
    if (cache_dir() / "data_plane.json").is_file():
        steps.append("data_plane")
    for name in ("regime", "narrative", "markets"):
        if _model_path(name).is_file():
            steps.append(name)
    return steps


def clear_checkpoint() -> None:
    if not cache_dir().exists():
        return
    for p in cache_dir().glob("*.json"):
        p.unlink(missing_ok=True)


def save_regime(r: RegimeReport) -> None:
    save_model("regime", r)


def load_regime() -> RegimeReport | None:
    return load_model("regime", RegimeReport)


def save_narrative(n: NarrativeReport) -> None:
    save_model("narrative", n)


def load_narrative() -> NarrativeReport | None:
    return load_model("narrative", NarrativeReport)


def save_markets(m: MarketsReport) -> None:
    save_model("markets", m)


def load_markets() -> MarketsReport | None:
    return load_model("markets", MarketsReport)
