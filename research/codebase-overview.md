# Investment Agent — Codebase Research Document

*Generated from live code inspection. Describes behavior as implemented today.*

---

## High-Level Summary

`investment-agent` (v0.1.0) is a Python multi-agent pipeline that produces a structured `InvestmentBrief` JSON report. The v2 pipeline uses three LLM agents (**Regime**, **Narrative**, **Markets**) that each receive disjoint inputs from a shared **Data Plane**; a programmatic **BriefAssembler** (no LLM) clusters and ranks themes into `FinalTheme` rows. Non-LLM data comes from Finnhub, TickerTick, and yfinance via `httpx` and `yfinance`. `ThemeOrchestrator.run()` fetches the Data Plane first, then runs the three agents in parallel via `ThreadPoolExecutor`, assembles the brief, and enriches metadata. Optional checkpoint resume persists steps under `reports/cache/`. Entry points are `main.py` / `invest-themes` (CLI) and `streamlit run streamlit_app.py` / `invest-dashboard` (UI). One unit test file exists at `tests/test_brief_assembler.py`.

---

## Repository Layout

```
investment_agent/
├── main.py                          # CLI entry shim
├── streamlit_app.py                 # Streamlit UI
├── pyproject.toml                   # deps, console scripts
├── .env.example                     # env var template
├── README.md                        # user-facing docs (v2)
├── research/                        # research documents
│   ├── codebase-overview.md         # this file
│   └── three-domain-agents-design.md
├── tests/
│   └── test_brief_assembler.py      # assembler unit test
└── src/investment_agent/
    ├── orchestrator.py              # v2 pipeline coordinator
    ├── data_plane.py                # external data fetch (pre-LLM)
    ├── inputs.py                    # disjoint agent input dataclasses
    ├── brief_assembler.py           # programmatic theme merge
    ├── checkpoint.py                # partial-run cache (v2 steps)
    ├── storage.py                   # latest.json persistence
    ├── models.py                    # Pydantic schemas
    ├── config.py                    # Settings.from_env()
    ├── llm.py                       # OpenAI-compatible structured JSON client
    ├── dates.py                     # analysis date helpers
    ├── errors.py                    # QuotaExhaustedError
    ├── themes.py                    # theme_key() helper
    ├── brief_compat.py              # backward-compatible brief accessors
    ├── market_data.py               # VolSnapshot
    ├── cli.py                       # CLI implementation
    ├── dashboard.py                 # streamlit launcher subprocess
    ├── agents/
    │   ├── regime_agent.py          # RegimeAgent
    │   ├── narrative_agent.py       # NarrativeAgent
    │   └── markets_agent.py         # MarketsAgent
    ├── news/                        # ingest + lexical RAG
    └── data/                        # yfinance fundamentals snapshot
```

Runtime artifacts (not in git by default): `reports/latest.json`, `reports/cache/*.json`.

---

## Entry Points

| Path | Role |
|------|------|
| `main.py:1-4` | Imports and calls `investment_agent.cli.main` |
| `src/investment_agent/cli.py:133-200` | `main()` — argparse, `ThemeOrchestrator.run()`, `save_brief()`, Rich print or `--json` |
| `streamlit_app.py:328-424` | `main()` — sidebar controls, run orchestrator, render `InvestmentBrief` |
| `src/investment_agent/dashboard.py:6-9` | `main()` — subprocess `streamlit run streamlit_app.py` |
| `pyproject.toml:17-19` | Console scripts `invest-themes`, `invest-dashboard` |

`streamlit_app.py:9-12` inserts `src/` on `sys.path` when run directly.

---

## Configuration (`config.py`)

`Settings` is a frozen dataclass loaded via `Settings.from_env()` (`config.py:22-86`).

| Field | Source |
|-------|--------|
| `api_key`, `base_url`, `model`, `provider` | `GEMINI_*` or `OPENAI_*` env vars |
| `market_region` | `MARKET_REGION` (default `global`) |
| `finnhub_api_key` | `FINNHUB_API_KEY` |
| `news_max_articles` | `NEWS_MAX_ARTICLES` (default 40) |
| `rag_top_k` | `RAG_TOP_K` (default 12) |
| `pipeline_version` | `PIPELINE_VERSION` (default 2) |

Provider resolution order (`config.py:36-76`): explicit `LLM_PROVIDER=gemini` → `OPENAI_API_KEY` → fallback `GEMINI_API_KEY`; raises `ValueError` if no key.

Gemini default base URL: `https://generativelanguage.googleapis.com/v1beta/openai/` (`config.py:8`). Default model: `gemini-2.0-flash` (`config.py:9`).

`Settings.pipeline_version` is loaded from env (`config.py:32,84`) but is not read by `orchestrator.py` or `checkpoint.py` at runtime; `checkpoint.py` uses its own module constant `PIPELINE_VERSION = 2` (`checkpoint.py:26`).

---

## Data Models (`models.py`)

### Theme lifecycle

`ThemeStage` enum: `early`, `early_mid`, `mid`, `mid_late`, `late` (`models.py:7-21`). Labels in `STAGE_LABELS` (`models.py:23-29`).

### Per-agent theme row

`AgentTheme` (`models.py:49-64`): `name`, `subtitle` (alias `name_zh`), `thesis`, `stage`, `stage_rationale`, `confidence`, `key_drivers`, `risks`, `tickers_or_sectors`.

### v2 agent reports (active pipeline)

| Model | Key fields | Lines |
|-------|------------|-------|
| `RegimeReport` | `macro_backdrop`, `dominant_regime`, `themes`, `cross_asset_signals` | `87-93` |
| `NarrativeReport` | `news_backdrop`, `narrative_sentiment`, `citations`, `themes`, RAG metadata, sourced drivers/risks | `96-108` |
| `MarketsReport` | `market_style`, `vol_regime`, `equity_view`, `quant_view`, `equity_themes`, `quant_themes`, `valuation_notes`, `vol_signals` | `111-122` |

### v1 report types (retained in schema, not used by current agents)

`MacroReport` (`models.py:80-84`), `EquityReport` (`models.py:125-128`), `QuantReport` (`models.py:131-135`), `NewsReport` (`models.py:138-148`) — structurally similar to v2 counterparts.

### Assembler / final output

`FinalTheme` (`models.py:151-182`): merged theme with `consensus_score`, `investability_score`, `contributing_agents`, `primary_agent`, `agent_stages`, `synthesis`, sourced drivers/risks. Agent labels in `contributing_agents` / `primary_agent` use legacy keys `macro`, `news`, `equity`, `quant` (`brief_assembler.py:27,37-43`).

`InvestmentBrief` (`models.py:185-210`): final report with four view fields (`macro_view`, `equity_view`, `quant_view`, `news_view`), merged `themes[]`, agent theme snapshots (`macro_themes` … `quant_themes`), `news_citations`, `fundamentals_notes`, `data_sources`, fixed `disclaimer`.

Supporting types: `NewsCitation` (`models.py:67-72`), `SourcedItem` (`models.py:75-77`).

---

## Input Contracts (`inputs.py`)

Disjoint dataclasses split from `DataPlaneSnapshot` (`inputs.py:13-54`):

| Type | Fields | Purpose |
|------|--------|---------|
| `RegimeInput` | `as_of`, `region` | Macro lens only (`inputs.py:13-18`) |
| `NarrativeInput` | `as_of`, `region`, `retrieval_query`, corpus counts, `ingest_notes`, `context_block`, `retrieved` | Pre-fetched RAG context (`inputs.py:21-32`) |
| `MarketsInput` | `as_of`, `region`, `fundamentals`, `vol` | Fundamentals + vol only (`inputs.py:35-42`) |
| `DataPlaneSnapshot` | `as_of`, `region`, three `*Input`, `data_plane_notes` | Container for one run (`inputs.py:45-54`) |

No cross-agent report fields appear in any `*Input`.

---

## Data Plane (`data_plane.py`)

`build_data_plane(settings, as_of=None)` (`data_plane.py:24-79`) runs all external fetches before any agent LLM call:

1. `build_news_retrieval_query(region)` → `fetch_news_articles` → `retrieve_articles` → `format_context_block` (`data_plane.py:33-40`)
2. `fetch_fundamentals_snapshot([], ...)` — empty theme list → fixed sector ETF universe (`data_plane.py:43-47`)
3. `fetch_vol_snapshot()` (`data_plane.py:50-52`)
4. Assembles `RegimeInput`, `NarrativeInput`, `MarketsInput` into `DataPlaneSnapshot` (`data_plane.py:54-79`)

`data_plane_notes` collects ingest notes, fundamentals row count, and vol notes (`data_plane.py:31,41,48-52`).

---

## Orchestration (`orchestrator.py`)

### `ThemeOrchestrator`

Constructs one shared `LLMClient` and three agents (`orchestrator.py:25-30`).

### `run(resume=None)` pipeline (`orchestrator.py:32-97`)

| Step | Action | Checkpoint name |
|------|--------|-----------------|
| 0 | Meta check / `save_run_meta` | `run_meta.json` |
| 1 | `build_data_plane()` or `load_data_plane()` | `data_plane` |
| 2 | `RegimeAgent.analyze(regime_input)` | `regime` |
| 3 | `NarrativeAgent.analyze(narrative_input)` | `narrative` |
| 4 | `MarketsAgent.analyze(markets_input)` | `markets` |
| 5 | `assemble(regime, narrative, markets)` | not checkpointed |
| 6 | `_enrich_brief()` | — |
| 7 | `clear_checkpoint()` on success | — |

Steps 2–4 run in parallel when pending (`orchestrator.py:60-83`) via `ThreadPoolExecutor(max_workers=3)`. Each completed agent is checkpointed immediately in the `as_completed` loop (`orchestrator.py:69-83`).

`as_of` date from `analysis_date()` (`dates.py:14-16`). Resume controlled by `checkpoint.is_resume_enabled()` unless `resume` arg overrides (`orchestrator.py:35`). Mismatched `as_of`/`region`/`pipeline_version` clears cache (`orchestrator.py:37-38`, `checkpoint.py:68-74`).

Agents do not receive each other's reports. The only shared object is `DataPlaneSnapshot`, split into disjoint inputs.

### `_enrich_brief()` (`orchestrator.py:99-154`)

Programmatic updates after assembler:

- Normalizes `FinalTheme.stage` / `stage_label` (`orchestrator.py:110-120`)
- Sets `report_date`, `as_of_context` via `build_as_of_context` (`orchestrator.py:138-143`, `dates.py:45-66`)
- Builds `data_sources` list (`orchestrator.py:122-132`)
- `fundamentals_notes` from `plane.markets_input.fundamentals.summary_lines()` (`orchestrator.py:134,148`)
- Maps v2 reports to compatibility snapshot fields: `macro_themes` ← `regime.themes`, `news_themes` ← `narrative.themes`, `equity_themes` / `quant_themes` ← `markets` (`orchestrator.py:149-152`)
- `news_citations` ← `narrative.citations` (`orchestrator.py:146`)

### `compute_stage_consensus()` (`orchestrator.py:157-178`)

Debug helper: maps `theme_key(name)` → per-agent stages using labels `macro`, `news`, `equity`, `quant`.

---

## Brief Assembler (`brief_assembler.py`)

Programmatic merge — no LLM (`brief_assembler.py:1`).

### Theme collection and clustering

`_collect_tagged()` tags themes with compat agent labels (`brief_assembler.py:30-44`):

- `RegimeReport.themes` → `macro`
- `NarrativeReport.themes` → `news`
- `MarketsReport.equity_themes` → `equity`
- `MarketsReport.quant_themes` → `quant`

Clusters by `theme_key(item.theme.name)` (`brief_assembler.py:121-124`, `themes.py:10-14`).

### Per-cluster merge (`brief_assembler.py:127-158`)

| Field | Rule |
|-------|------|
| `name`, `subtitle`, `thesis` | From highest-`confidence` theme (`primary`) |
| `stage` | From highest-confidence theme (`_pick_stage`, `brief_assembler.py:47-49,130`) |
| `investability_score` | Mean confidence, clamped 0–1 (`brief_assembler.py:131,147`) |
| `consensus_score` | `min(1.0, len(agents) / 2.0)` (`brief_assembler.py:132`) |
| `contributing_agents` | Sorted unique agent labels (`brief_assembler.py:128,149`) |
| `primary_agent` | Agent label of highest-confidence theme (`brief_assembler.py:150`) |
| `agent_stages` | Map agent → stage for each theme in cluster (`brief_assembler.py:133,148`) |
| `synthesis` | First two `stage_rationale` strings joined, else primary thesis (`brief_assembler.py:136-137,151`) |
| `key_drivers`, `risks`, `tickers_or_sectors` | Deduped merge, capped at 6/5/8 (`brief_assembler.py:52-82,152-154`) |
| `key_drivers_sourced`, `risks_sourced` | Token overlap with narrative cluster anchor (`brief_assembler.py:89-111,155-156`) |

### Post-processing (`brief_assembler.py:160-186`)

- Sort by `investability_score` descending; keep top 8 (`brief_assembler.py:160-161`)
- If fewer than 4 themes, backfill unclustered themes by exact name match (`brief_assembler.py:162-186`)

### View and summary fields (`brief_assembler.py:188-223`)

- `executive_summary`: concatenation of `macro_backdrop`, `narrative_sentiment`, `news_backdrop`, top theme names (`brief_assembler.py:188-193`)
- `macro_view`: backdrop + `dominant_regime` + cross-asset signals (`brief_assembler.py:195-198`)
- `news_view`: `narrative.news_backdrop` (`brief_assembler.py:199`)
- `equity_view` / `quant_view`: from `MarketsReport` or fallback from `market_style`/`valuation_notes` and `vol_regime`/`vol_signals` (`brief_assembler.py:200-205`)

---

## Agent — Regime (`agents/regime_agent.py`)

- **External data:** none; single `LLMClient.structured` call (`regime_agent.py:46-57`).
- **Input:** `RegimeInput` (`as_of`, `region`).
- **Output:** `RegimeReport` with 4–6 macro themes per prompt (`regime_agent.py:8,56`).
- **Prompt:** `SYSTEM` (`regime_agent.py:6-39`) defines five lifecycle stages and JSON schema.

---

## Agent — Narrative (`agents/narrative_agent.py`)

- **External data:** pre-fetched in Data Plane; agent receives `NarrativeInput.context_block` only.
- **Input:** `NarrativeInput` (`narrative_agent.py:41-57`).
- **Output:** `NarrativeReport` with 3–6 news-driven themes (`narrative_agent.py:15,57`).
- **Post-process:** citation backfill from `inp.retrieved` when LLM returns fewer citations (`narrative_agent.py:62-90`); copies `retrieval_query`, `articles_retrieved`, `ingest_notes` from input.

---

## Agent — Markets (`agents/markets_agent.py`)

- **External data:** `FundamentalsSnapshot.to_prompt_block()` and `VolSnapshot.to_prompt_block()` (`markets_agent.py:46-47,55-57`).
- **Input:** `MarketsInput` (no other agent outputs).
- **Output:** `MarketsReport` with `equity_themes` (3–5) and `quant_themes` (3–5) in one LLM call (`markets_agent.py:8-10,59-61`).
- **Prompt:** `SYSTEM` (`markets_agent.py:6-38`) combines equity fundamentals and vol/risk lenses.

---

## News Ingest (`news/ingest.py`)

| Provider | Endpoint | ID prefix | Lines |
|----------|----------|-----------|-------|
| Finnhub | `https://finnhub.io/api/v1/news` | `fh-` | `14-15`, `47-85` |
| TickerTick | `https://api.tickertick.com/feed` | `tt-` | `13`, `88-127` |

`NewsArticle` dataclass (`ingest.py:17-29`). Dedup by title prefix (`ingest.py:130-139`). Region affects Finnhub category and TickerTick query (`ingest.py:154-172`).

`fetch_news_articles()` returns `(articles, ingest_notes)` (`ingest.py:142-177`).

---

## Lexical RAG (`news/rag.py`)

- `build_news_retrieval_query(region)` — region + market-wide terms only (`rag.py:16-29`). Used by Data Plane.
- `build_retrieval_query(region, theme_names, macro_backdrop)` — legacy helper with macro theme names (`rag.py:32-48`); not called by current pipeline.
- `retrieve_articles()`: token overlap scoring, title boost 2× (`rag.py:51-81`).
- `format_context_block()` — article blocks with IDs for LLM context (`rag.py:84-93`).

---

## Market Data — Volatility (`market_data.py`)

`fetch_vol_snapshot()` (`market_data.py:28-67`):

- Symbols: `^VIX`, `XLK`, `XLE`, `XLV`, `XLF`, `IGV` (`market_data.py:39-46`).
- Computes VIX level, 20d change, 20d annualized vol per sector ETF.
- Returns `VolSnapshot` with `notes` on failures (`market_data.py:8-14`).

---

## Market Data — Fundamentals (`data/`)

### Universe (`data/universe.py`)

- `SECTOR_ETFS` — 8 sector labels → symbols (`universe.py:8-17`).
- `BENCHMARK_SYMBOL = "SPY"` (`universe.py:19`).
- `symbols_for_fundamentals()` — sectors + SPY + optional theme tickers capped by `FUNDAMENTALS_MAX_TICKERS` (`universe.py:44-77`).

### Snapshot fetch (`data/snapshot.py`)

`fetch_fundamentals_snapshot(themes, ...)` (`snapshot.py:155-214`):

- Data Plane passes `[]` for themes (`data_plane.py:43-44`) → fixed ETF universe only.
- Parallel fetch via `ThreadPoolExecutor` (`snapshot.py:177-196`).
- Per symbol: `fetch_price_metrics`, `fetch_valuation_metrics`, optional `fetch_revision_metrics` for non-ETF symbols when Finnhub key present (`snapshot.py:131-152`, `180-181`).
- Rule-based `signals` via `_build_signals()` (`snapshot.py:97-128`).

### Price (`data/price.py:32-66`)

yfinance 1y history → `last_close`, 20d/60d returns, vs 52w high, vs SPY 20d.

### Valuation (`data/valuation.py:30-49`)

yfinance `.info` → trailing/forward P/E, P/B, market cap.

### Revisions (`data/revisions.py:40-91`)

Finnhub `GET /stock/recommendation` → `revision_proxy` = (strongBuy+buy−sell−strongSell)/total.

---

## LLM Client (`llm.py`)

`LLMClient` wraps `openai.OpenAI` with `settings.api_key` and `settings.base_url` (`llm.py:71-77`).

`structured(system, user, schema, temperature=0.3)` (`llm.py:79-157`):

1. Appends JSON schema to system prompt (`llm.py:87-93`).
2. Calls `chat.completions.create` with `response_format=json_object` first, retries without (`llm.py:100-111`).
3. Parses response via `_extract_json` (strips markdown fences, `llm.py:23-28`).
4. Validates with Pydantic `schema.model_validate`.
5. On 429: retries up to `LLM_MAX_RETRIES_ON_429` (default 2, `llm.py:63-68`), then raises `QuotaExhaustedError` (`errors.py:6-40`).

---

## Checkpoint (`checkpoint.py`)

- Directory: `reports/cache/` relative to repo root (`checkpoint.py:24`).
- Enabled when `RESUME_CHECKPOINT` is `1`/`true`/`yes`/`on` (`checkpoint.py:29-37`).
- `run_meta.json` stores `{as_of, region, pipeline_version}` (`checkpoint.py:45-55`).
- `meta_matches()` requires `pipeline_version == 2` (`checkpoint.py:68-74`).
- Per-step files: `data_plane.json` (custom serialization), `regime.json`, `narrative.json`, `markets.json` (Pydantic JSON) (`checkpoint.py:146-263`).
- `list_checkpoint_steps()` returns `data_plane`, `regime`, `narrative`, `markets` as applicable (`checkpoint.py:225-232`).
- `clear_checkpoint()` deletes all `*.json` in cache dir (`checkpoint.py:235-239`).
- Successful full run clears checkpoint (`orchestrator.py:95-96`).

---

## Persistence (`storage.py`)

- Default path: `reports/latest.json` (`storage.py:8`).
- `save_brief()` — `model_dump_json(by_alias=True)` (`storage.py:11-18`).
- `load_brief()` — validates via `migrate_brief_dict()` from `brief_compat.py` (`storage.py:21-27`, `brief_compat.py:49-66`).
- `_normalize_loaded_brief()` backfills `report_date` / `as_of_context` for older reports (`storage.py:35-52`).

---

## UI Layer

### Streamlit (`streamlit_app.py`)

- Sidebar: region select, run, resume checkbox, checkpoint clear, load cache (`streamlit_app.py:334-367`).
- Run: `ThemeOrchestrator(settings).run(resume=resume_ckpt)` + `save_brief()` (`streamlit_app.py:385-387`).
- Agent tabs: Regime, Narrative, Markets (equity + quant in one tab) (`streamlit_app.py:257-273`).
- Pre-merge themes in 4 columns using compat labels macro/news/equity/quant (`streamlit_app.py:275-285`, `AGENT_LABELS` at `streamlit_app.py:64-69`).
- Theme cards sorted by `investability_score` (`streamlit_app.py:308-323`).

### CLI (`cli.py`)

- `print_brief()` — Rich panels and theme table (`cli.py:40-130`).
- View labels: Regime, Narrative, Markets (equity), Markets (quant) (`cli.py:53-58`).
- Handles `QuotaExhaustedError` with checkpoint step listing (`cli.py:183-188`).

---

## End-to-End Data Flow

```
Settings.from_env()
       │
       ▼
ThemeOrchestrator.run()
       │
       ├─► build_data_plane()     (Finnhub + TickerTick + yfinance — no LLM)
       │         │
       │         ├─► RegimeInput
       │         ├─► NarrativeInput
       │         └─► MarketsInput
       │
       ├─► RegimeReport           (LLM)  ─┐
       ├─► NarrativeReport        (LLM)  ─┼─ parallel ThreadPoolExecutor
       ├─► MarketsReport           (LLM)  ─┘
       │
       ├─► assemble()             (programmatic BriefAssembler)
       └─► _enrich_brief()        (dates, citations, snapshots, data_sources)
                │
                ▼
         save_brief() → reports/latest.json
```

**LLM calls per full run:** 3 (regime, narrative, markets).

**HTTP external services:**

| Service | Used by | Library |
|---------|---------|---------|
| Gemini/OpenAI compatible API | Three agents | `openai` |
| Finnhub news | `news/ingest.py` | `httpx` |
| Finnhub recommendations | `data/revisions.py` | `httpx` |
| TickerTick feed | `news/ingest.py` | `httpx` |
| Yahoo Finance | `market_data.py`, `data/price.py`, `data/valuation.py` | `yfinance` |

---

## Python Dependencies (`pyproject.toml:7-15`)

`openai`, `pydantic`, `python-dotenv`, `rich`, `yfinance`, `streamlit`, `httpx`. Requires Python `>=3.11`.

`pyproject.toml:4` description string still references the prior four-agent layout.

---

## Tests

| File | Coverage |
|------|----------|
| `tests/test_brief_assembler.py:29-66` | `assemble()` clustering, view mapping, narrative sourced-item attachment on matching cluster |

Test uses pytest-style `assert` functions. `pytest` is not listed in `pyproject.toml` dependencies.

---

## Cross-Component Connections Summary

| From | To | What flows |
|------|-----|------------|
| `config.Settings` | Data Plane, `LLMClient`, agents (via orchestrator) | API keys, region, news/RAG limits |
| `build_data_plane()` | `RegimeInput`, `NarrativeInput`, `MarketsInput` | Disjoint slices of fetched data |
| `RegimeReport` | `BriefAssembler`, `_enrich_brief` | Themes → `macro_themes`; backdrop → `macro_view` |
| `NarrativeReport` | `BriefAssembler`, `_enrich_brief` | Themes → `news_themes`; citations → `news_citations` |
| `MarketsReport` | `BriefAssembler`, `_enrich_brief` | `equity_themes` / `quant_themes`; views |
| `FundamentalsSnapshot` | `MarketsAgent`, `_enrich_brief` | Prompt block; `fundamentals_notes` |
| `VolSnapshot` | `MarketsAgent` | `to_prompt_block()` |
| Three `*Report` | `brief_assembler.assemble()` | Programmatic merge → `InvestmentBrief.themes[]` |
| `theme_key()` | `brief_assembler` | Cluster identity for merge |
| `brief_compat` | `storage.load_brief`, CLI, Streamlit | Safe field access, schema migration |
| `checkpoint` | `orchestrator`, CLI, Streamlit | Resume on 429 / partial failure |

---

## Agent Module Exports (`agents/__init__.py`)

```python
RegimeAgent, NarrativeAgent, MarketsAgent
```

Prior v1 agent modules (`macro_economist.py`, `news_analyst.py`, `equity_analyst.py`, `quant_analyst.py`) are not present in the current tree.
