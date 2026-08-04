# Agent instructions — investment_agent

Guidance for AI coding agents working in this repository. Human-oriented setup and architecture live in [README.md](./README.md).

## What this project is

Multi-agent **investment theme analysis** (v2): three domain agents (Regime, Narrative, Markets) read **disjoint inputs** from a shared data plane; `brief_assembler.py` merges themes by sector, scores them, and ranks by investability + consensus. **Three LLM calls per run.** All agent-facing outputs are **English**.

## Non-negotiable architecture

1. **Fetch and slice before any LLM.** External I/O belongs in `*/input.py`, `ingest.py`, `snapshot.py`, or `data_plane.py` — never in `agents/*/agent.py`.
2. **Agents do not see each other's reports.** Each agent gets only its own `*Input` frozen object.
3. **`brief_assembler.py` is programmatic** — no LLM, no HTTP.
4. **Single yfinance fetch per run** via `agents/markets/input.fetch_market_snapshots()`; Regime and Markets share that snapshot.
5. **Narrative layering** (do not collapse):
   - `ingest.py` — Finnhub + TickerTick → `NewsArticle[]`
   - `rag.py` — hybrid retrieval (lexical + `sentence-transformers` RRF) + `format_context_block`
   - `input.py` — `build_narrative_input()` → `NarrativeInput`
   - `agent.py` — one LLM call; uses `context_block` only

```
data_plane.build_data_plane()  →  Regime / Narrative / Markets *Input
orchestrator                   →  3 × Agent.analyze()  →  brief_assembler.assemble()
```

## Where to change things

| Goal | Location |
|------|----------|
| Sector ETFs, ticker→sector map | `src/investment_agent/universe/constants.py` |
| Theme merge, scoring, rank | `brief_assembler.py` |
| News sources / corpus | `agents/narrative/ingest.py` |
| RAG retrieval / context caps | `agents/narrative/rag.py`, `config.py` |
| Macro context slice | `agents/regime/input.py` |
| Fundamentals / vol snapshots | `agents/markets/snapshot.py`, `input.py` |
| LLM provider, rate limits, RAG defaults | `config.py`, `.env.example` |
| Checkpoint / resume | `checkpoint.py` (`PIPELINE_VERSION`) |
| Persist brief JSON | `storage.py` |
| GitHub-readable brief (Markdown + JSON for Streamlit Cloud) | `report_markdown.py`, `brief/` |
| Portfolio ledger / alignment UI | `portfolio/manual/`, `portfolio/model/`, `portfolio/compare/`, `streamlit_app.py` |
| Single-stock research | `stock_research/`, View → **Stock** in `streamlit_app.py` (`stock_research/streamlit_ui.py`) |
| Design notes (not runtime) | `research/` |

## Theme stages

Use consistently across agents and assembler:

| Code | Meaning |
|------|---------|
| `early` | Forming, not fully priced |
| `early_mid` | Thesis validating |
| `mid` | Trend confirmed |
| `mid_late` | Crowded, rich valuations |
| `late` | Overheated — exit watch |

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env   # set GEMINI_API_KEY or OPENAI_API_KEY

pytest tests/          # run before finishing substantive changes
python main.py         # or: invest-themes
streamlit run streamlit_app.py   # invest-dashboard (Themes · Portfolio · Stock)
invest-stock AAPL                # single-stock memo CLI
```

After changing `config.py` defaults or `RAG_*` env vars: **restart** Streamlit/CLI. If Narrative prompt is too large or context looks stale, **clear checkpoint** (`reports/cache/` or Streamlit UI).

### Groq / token limits

Groq on-demand is ~12k tokens/request. When `base_url` contains `groq.com`, `config.py` auto-caps `NEWS_MAX_ARTICLES`, `RAG_TOP_K`, `RAG_CONTEXT_MAX_CHARS`. Do not inflate narrative context without checking Groq limits. OpenRouter `:free` models run agents **sequentially** by default. Single-stock research uses **5 LLM calls**; cap context with `STOCK_RESEARCH_CONTEXT_MAX_CHARS`.

### Hybrid RAG

`RAG_HYBRID=1` (default) loads `all-MiniLM-L6-v2` on first use (~80MB). Set `RAG_HYBRID=0` for lexical-only. Tests mock embeddings in `tests/test_rag_hybrid.py`.

## Coding standards

- **Minimal diffs** — match existing style; no drive-by refactors.
- **Reuse** `universe/`, `models.py`, and existing input builders; do not duplicate sector maps.
- **Comments** only for non-obvious business logic.
- **Tests** for real behavior changes; avoid trivial assertions.
- **Do not** add markdown docs unless the user asks.
- **Do not** commit unless explicitly requested.

## Do not

- Commit `.env`, API keys, or `reports/` (gitignored). `brief/` is tracked for GitHub Actions publish.
- Call `httpx` or yfinance inside `agents/*/agent.py` or `stock_research/*/agent.py`.
- Wire one theme agent's output into another agent's input (only assembler merges). For stock research, **only** the Reasoning agent may see other domain reports.
- Force-push `main`.
- Over-abstract (one-off helpers, excessive error handling for unlikely paths).

## Portfolio subsystem (separate from theme pipeline)

Two SQLite ledgers exist in code (`manual` / `model`), but **Streamlit trades are manual only**. Subpackages: `portfolio/manual/` (trades + theme alignment), `portfolio/model/` (brief-driven benchmarks, no trade UI), `portfolio/compare/` (manual vs brief target). `portfolio/manual/theme_alignment.py` is **diagnostic only** — not rebalance or trade suggestions.

## Stock research subsystem (separate from theme pipeline)

Independent package `stock_research/`: Business / Financial / Valuation / Expectation (disjoint inputs from `bundle.py`) then Reasoning → `InvestmentMemo`. **Do not** fold into `ThemeOrchestrator`. Unified UI: `streamlit_app.py` → View → **Stock** (`stock_research/streamlit_ui.py`). Optional standalone: `stock_research_app.py`. Checkpoint: `reports/cache/stock_research/{TICKER}/`.

## CI

[`.github/workflows/weekly-brief.yml`](.github/workflows/weekly-brief.yml) runs the pipeline and commits `brief/latest.md`. Workflow commits use `[skip ci]`.

## When unsure

Read `README.md` architecture section and the relevant `agents/<name>/input.py` before editing `agent.py` or `orchestrator.py`.
