# Design: Three-Domain Agents + Programmatic Brief Assembler

| Field | Value |
|-------|-------|
| Status | Draft — plan only (no implementation) |
| Pipeline version | `2` (target) |
| Research basis | `research/codebase-overview.md` |
| Proposal | Proposal 2 — three domain agents, disjoint inputs, no CIO LLM |

> **Note:** `design_doc_template.md` was not present in the repository. This document follows the requested sections: current context, requirements, design decisions, implementation plan, plus testing/rollout where they affect the change.

---

## Scope Summary (read first)

### In scope

- Replace 4 specialist agents + CIO LLM with **3 analysis agents** + **1 programmatic `BriefAssembler`**
- Introduce **Data Plane** (all HTTP/yfinance fetch before any LLM call)
- Introduce **strict `*Input` Pydantic models** — no agent receives another agent’s output
- Reduce LLM calls per full run: **5 → 3**
- Update orchestrator, checkpoint, `brief_compat`, CLI, Streamlit, README, `.env.example`
- Backward load of old `reports/latest.json` via `brief_compat.migrate_brief_dict`

### Out of scope

- New external data providers (Google CSE, FRED, Bloomberg)
- Vector embeddings / new RAG stack
- Changing `LLMClient` (`llm.py`) behavior
- Removing or rewriting `news/` ingest/RAG internals (reuse as-is from Data Plane)
- CI/CD pipeline setup
- Dual-run `PIPELINE_VERSION=1` maintenance long-term (v1 code may remain behind deprecation shim for one release)

### Constraints

- **Python ≥ 3.11**; no new required dependencies (`pyproject.toml:7-15`)
- **Agent input isolation:** `*Input` field sets must be pairwise disjoint; `analyze()` signatures must not accept `*Report` from other agents
- **Preserve `InvestmentBrief` consumer contract** where feasible: `themes[]`, `news_citations`, `fundamentals_notes`, four view fields (`macro_view` … `quant_view`) populated by Assembler mapping — not by cross-agent prompts
- **Checkpoint resume** must work for 3 agent steps + optional data plane cache (`checkpoint.py` pattern)
- **English-only** agent outputs (unchanged)
- **No tests directory today** (`research/codebase-overview.md:345-347`) — minimal tests added only for Assembler + Input contracts

### Timeline (estimate)

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| 0 — Contracts | 1–2 days | `inputs.py`, `data_plane.py`, new report models in `models.py` |
| 1 — Agents | 2–3 days | `RegimeAgent`, `NarrativeAgent`, `MarketsAgent`; deprecate old four agents |
| 2 — Assembler + orchestrator | 2 days | `brief_assembler.py`, rewrite `ThemeOrchestrator.run()` |
| 3 — Persistence + UI | 1–2 days | checkpoint, `brief_compat`, `streamlit_app.py`, `cli.py` |
| 4 — Docs + validation | 1 day | README, manual smoke runs, remove dead imports |

**Total:** ~7–10 working days for one developer.

---

## Current Context

- Pipeline today: sequential **Macro → News → Fundamentals fetch → Equity → Quant → CIO LLM → enrich** (`orchestrator.py:100-165`, `research/codebase-overview.md:125-137`).
- **5 LLM calls** per run (`research/codebase-overview.md:325`).
- **Input coupling** (violates desired separation):
  - Equity accepts `NewsReport`; uses `news_backdrop` + `narrative_sentiment` only (`equity_analyst.py:43-59`).
  - Quant accepts `macro.dominant_regime` (`orchestrator.py:143-146`, `quant_analyst.py:49-53`).
  - News ingest runs inside `NewsAnalyst.analyze()` (`news_analyst.py:54-58`), mixing data fetch with LLM.
- CIO merge is entirely LLM-driven (`orchestrator.py:35-88`, `167-201`); `compute_stage_consensus()` exists but is debug-only (`orchestrator.py:275-294`).
- UI exposes **4 agent tabs** + pre-merge theme expander (`streamlit_app.py:256-284`).
- User goal: **fewer roles, structurally clear agents, each with its own input only.**

---

## Requirements

### Functional

- **R1:** Three analysis agents, each callable as `agent.analyze(inp: XInput) -> XReport`.
- **R2:** Data Plane builds all external inputs once; agents never call `httpx` / `yfinance` directly (NarrativeAgent receives pre-retrieved articles).
- **R3:** `BriefAssembler` produces `InvestmentBrief` with ranked `FinalTheme[]` without an LLM call.
- **R4:** `MarketsAgent` replaces Equity + Quant; output includes distinguishable equity- and quant-lens themes (sub-lists or `lens` field on `AgentTheme`).
- **R5:** `NarrativeAgent` preserves news citations and RAG behavior equivalent to current `NewsAnalyst` (`news_analyst.py:50-112`).
- **R6:** `RegimeAgent` preserves macro theme discovery equivalent to current `MacroEconomist` (`macro_economist.py:49-61`).
- **R7:** Entry points (`main.py`, `cli.py`, `streamlit_app.py`) run v2 pipeline by default after rollout.
- **R8:** `RESUME_CHECKPOINT` saves/loads `regime`, `narrative`, `markets` (+ optional `data_plane`).

### Non-functional

- **NR1:** Full run uses **≤ 3 LLM requests** (down from 5).
- **NR2:** Agents 2 and 3 may run in parallel after Data Plane (Regime can run parallel with Narrative+Markets data prep; Markets LLM waits on fundamentals + vol).
- **NR3:** Old `reports/latest.json` loads without crash (`storage.py:21-27`, `brief_compat.py:49-66`).

---

## Design Decisions

| ID | Decision | Rationale |
|----|----------|-----------|
| D1 | **Data Plane first** | Single place for Finnhub/TickerTick/yfinance; agents become pure LLM+Input→Report |
| D2 | **Three agents: Regime, Narrative, Markets** | Maps 1:1 to macro / news / (equity+quant) data families; reduces “5 roles” clutter |
| D3 | **Programmatic `BriefAssembler` only** | Deterministic merge; drops 5th LLM; reuses `theme_key()` (`themes.py:10-14`) |
| D4 | **`MarketsReport` holds `equity_themes` + `quant_themes`** | Preserves CIO trace fields on `InvestmentBrief` (`macro_themes`…`quant_themes`) without separate agents |
| D5 | **Map views for compatibility** | Assembler sets `macro_view`←regime, `news_view`←narrative, `equity_view`/`quant_view`←markets sections — avoids breaking CLI/Streamlit text layout |
| D6 | **Remove `dominant_regime` → Quant path** | Eliminates cross-agent dependency; regime context lives only in RegimeAgent output until Assembler |
| D7 | **Remove News → Equity path** | Equity lens inside MarketsAgent uses fundamentals+vol only; narrative overlap handled at Assembler via `theme_key` clustering |
| D8 | **`PIPELINE_VERSION=2` env** | Optional guard during migration; default `2` when implemented |
| D9 | **Deprecate, don’t delete v1 agents in phase 1** | Keep `macro_economist.py` etc. until v2 validated; remove in phase 4 |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Entry: cli.py / streamlit_app.py / main.py              │
└───────────────────────────┬─────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────┐
│  ThemeOrchestrator.run()  [v2]                           │
│    1. build_data_plane() → DataPlaneSnapshot             │
│    2. parallel: RegimeAgent / NarrativeAgent / MarketsAgent│
│    3. BriefAssembler.assemble() → InvestmentBrief        │
│    4. _enrich_brief() [slimmed — no CIO fields]          │
└─────────────────────────────────────────────────────────┘

DataPlaneSnapshot (disjoint slices → *Input)
├── regime_slice    → RegimeInput    { as_of, region }
├── narrative_slice → NarrativeInput { as_of, region, articles, query, ingest_notes }
└── markets_slice   → MarketsInput   { as_of, region, fundamentals, vol }
```

### New / modified modules

| Module | Action |
|--------|--------|
| `src/investment_agent/inputs.py` | **Add** — `RegimeInput`, `NarrativeInput`, `MarketsInput`, `DataPlaneSnapshot` |
| `src/investment_agent/data_plane.py` | **Add** — `build_data_plane(settings, as_of)` |
| `src/investment_agent/agents/regime_agent.py` | **Add** — wraps macro prompt logic |
| `src/investment_agent/agents/narrative_agent.py` | **Add** — LLM only; no internal fetch |
| `src/investment_agent/agents/markets_agent.py` | **Add** — merged equity+quant prompt |
| `src/investment_agent/brief_assembler.py` | **Add** — `assemble(regime, narrative, markets, as_of) -> InvestmentBrief` |
| `src/investment_agent/models.py` | **Modify** — `RegimeReport`, `NarrativeReport`, `MarketsReport`; keep `InvestmentBrief` |
| `src/investment_agent/orchestrator.py` | **Rewrite** `run()`; remove `SYNTHESIS_SYSTEM`, `_synthesize()` |
| `src/investment_agent/checkpoint.py` | **Modify** — step names `regime`, `narrative`, `markets`, `data_plane` |
| `src/investment_agent/agents/__init__.py` | **Modify** — export three agents |
| `src/investment_agent/brief_compat.py` | **Modify** — v1 brief field defaults unchanged |
| `streamlit_app.py` | **Modify** — 3 tabs; update agent labels |
| `cli.py` | **Modify** — agent progress text |
| `README.md`, `.env.example` | **Modify** — architecture diagram, `PIPELINE_VERSION` |

### Assembler logic (high level)

1. Collect all `AgentTheme` rows with source tag: `regime`, `narrative`, `equity`, `quant`.
2. Cluster by `theme_key(name)` (`themes.py:10-14`).
3. Per cluster: `contributing_agents`, `agent_stages`, `consensus_score` = min(1.0, n_agents / 2).
4. `investability_score`: mean of `confidence` in cluster (clamp 0–1).
5. `primary_agent`: agent with highest `confidence` in cluster.
6. `key_drivers_sourced` / `risks_sourced`: pass through from `NarrativeReport` when `citation_ids` match.
7. `executive_summary`: template string from regime backdrop + narrative backdrop + top 2 themes (no LLM).

---

## Implementation Plan

### Phase 0 — Contracts (1–2 days)

- [ ] Add `inputs.py` with four dataclasses/Pydantic models; document disjoint field sets in docstrings.
- [ ] Add `RegimeReport`, `NarrativeReport`, `MarketsReport` to `models.py` (or alias `MacroReport`→`RegimeReport` initially).
- [ ] Add `data_plane.py`:
  - Call `fetch_news_articles`, `build_news_retrieval_query`, `retrieve_articles` (`news/`)
  - Call `fetch_fundamentals_snapshot([])` (`data/snapshot.py:155-214`)
  - Call `fetch_vol_snapshot()` (`market_data.py:28-67`)
  - Return `DataPlaneSnapshot` + build three `*Input` instances.

### Phase 1 — Three agents (2–3 days)

- [ ] `RegimeAgent`: move `SYSTEM` + user template from `macro_economist.py:8-61`; `analyze(RegimeInput)`.
- [ ] `NarrativeAgent`: move prompt from `news_analyst.py`; accept pre-built context block from `NarrativeInput`; keep citation backfill (`news_analyst.py:81-111`).
- [ ] `MarketsAgent`: merge `equity_analyst.py` + `quant_analyst.py` prompts; single `MarketsInput`; output `MarketsReport` with `equity_themes`, `quant_themes`, `market_style`, `vol_regime`, `valuation_notes`, `vol_signals`.
- [ ] Update `agents/__init__.py` exports.

### Phase 2 — Assembler + orchestrator (2 days)

- [ ] Implement `brief_assembler.py` per Assembler logic above.
- [ ] Rewrite `ThemeOrchestrator.run()`:
  - Data Plane → checkpoint optional
  - Run three agents (thread pool for narrative ∥ regime after data ready; markets after data ready)
  - `BriefAssembler.assemble()` → slim `_enrich_brief()` (dates, citations, data_sources, theme snapshots)
- [ ] Delete or gate `_synthesize()`, `SYNTHESIS_SYSTEM` (`orchestrator.py:35-88`).
- [ ] Add `PIPELINE_VERSION` to `config.py` (default `2`).

### Phase 3 — Persistence + UI (1–2 days)

- [ ] `checkpoint.py`: `save_regime`/`load_regime`, etc.; update `list_checkpoint_steps()`.
- [ ] `brief_compat.py`: ensure old reports without v2 fields still load.
- [ ] `streamlit_app.py`: tabs `Regime | Narrative | Markets`; pre-merge expander shows three columns; update run status lines (`378-383`).
- [ ] `cli.py`: update progress labels; `print_brief` unchanged if view fields mapped.

### Phase 4 — Docs + cleanup (1 day)

- [ ] Update `README.md` architecture section and LLM call count.
- [ ] Update `research/codebase-overview.md` (separate pass after implementation).
- [ ] Remove deprecated agent files if v2 stable.
- [ ] Manual smoke: `invest-themes`, `streamlit run`, resume after simulated failure.

---

## Testing

- [ ] **Unit:** `theme_key` clustering — given fixed synthetic themes from three reports, assert cluster count and `contributing_agents`.
- [ ] **Unit:** `DataPlaneSnapshot` → three `*Input` builders; assert no shared mutable state between inputs.
- [ ] **Unit:** citation passthrough — narrative `citation_ids` appear on `FinalTheme.key_drivers_sourced`.
- [ ] **Integration (manual):** full run with `FINNHUB_API_KEY` set and unset; verify `ingest_notes` and fallbacks.
- [ ] **Regression:** load existing `reports/latest.json` from v1 into Streamlit “Load last result”.

---

## Observability

- [ ] Log per phase: data plane duration, per-agent LLM duration, assembler cluster count.
- [ ] Surface `ingest_notes` from Data Plane + Narrative in `InvestmentBrief.data_sources` or agent report metadata (existing pattern `news_analyst.py:69-70`).

---

## Rollout

- [ ] Ship behind `PIPELINE_VERSION=2` default; document `PIPELINE_VERSION=1` as unsupported after one release if v1 code removed.
- [ ] On first v2 run with old `reports/cache/*`, clear cache if step names mismatch (`checkpoint.meta_matches` pattern `checkpoint.py:58-63`).
- [ ] Update sidebar caption: “~3 LLM calls” (`streamlit_app.py:342`).

---

## Security

<!-- No change to secret handling; existing .env pattern for API keys unchanged. -->

---

## Open Questions

- [ ] `MarketsAgent` single LLM vs two sequential LLM calls inside one agent class (still 3 total) — default: **one** combined call.
- [ ] `executive_summary` template wording — product copy review needed.
- [ ] Whether to keep `compute_stage_consensus()` public API or fold into Assembler only.

---

## File Touch List (checklist)

| File | Change |
|------|--------|
| `src/investment_agent/inputs.py` | Add |
| `src/investment_agent/data_plane.py` | Add |
| `src/investment_agent/brief_assembler.py` | Add |
| `src/investment_agent/agents/regime_agent.py` | Add |
| `src/investment_agent/agents/narrative_agent.py` | Add |
| `src/investment_agent/agents/markets_agent.py` | Add |
| `src/investment_agent/models.py` | Modify |
| `src/investment_agent/orchestrator.py` | Rewrite |
| `src/investment_agent/checkpoint.py` | Modify |
| `src/investment_agent/config.py` | Modify |
| `src/investment_agent/agents/__init__.py` | Modify |
| `src/investment_agent/brief_compat.py` | Modify |
| `src/investment_agent/agents/macro_economist.py` | Deprecate → remove |
| `src/investment_agent/agents/news_analyst.py` | Deprecate → remove |
| `src/investment_agent/agents/equity_analyst.py` | Deprecate → remove |
| `src/investment_agent/agents/quant_analyst.py` | Deprecate → remove |
| `streamlit_app.py` | Modify |
| `src/investment_agent/cli.py` | Modify |
| `README.md` | Modify |
| `.env.example` | Modify |

**Untouched:** `llm.py`, `news/ingest.py`, `news/rag.py`, `data/price.py`, `data/valuation.py`, `data/revisions.py`, `market_data.py` (called from Data Plane only).
