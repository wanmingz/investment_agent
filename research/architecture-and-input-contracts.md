# Investment Agent — Architecture Layers & Input Contracts

*Generated from live code inspection. Describes behavior as implemented today.*

---

## High-Level Summary

当前代码库处于 **v2 三域 Agent 流水线**与 **v1 四 Agent + CIO 消费契约**的叠加状态：运行时只有 `RegimeAgent`、`NarrativeAgent`、`MarketsAgent` 三个 LLM 调用，但 `InvestmentBrief`、UI、`brief_assembler` 仍大量使用 v1 命名（`macro` / `news` / `equity` / `quant`）。**Regime（宏观）Agent 有输入类型 `RegimeInput`，但仅含 `as_of` 与 `region` 两个字段**；`build_data_plane()` 拉取的新闻、基本面、波动率数据均不注入 `RegimeInput`。Data Plane 在 orchestrator 中对三个 Agent 是共享入口，但 Regime 切片在数据面上为空操作——宏观分析完全依赖 LLM 参数化提示，无外部 API 数据块。Narrative 与 Markets 则分别接收预取 RAG 上下文和 yfinance/Finnhub 结构化快照。

---

## 1. 运行时结构（三层）

### 1.1 数据层 — Data Plane

`build_data_plane()`（`src/investment_agent/data_plane.py:24-79`）在任意 Agent LLM 调用之前顺序执行：

| 步骤 | 函数 | 产出用途 |
|------|------|----------|
| 1 | `fetch_news_articles` + `retrieve_articles` + `format_context_block` | `NarrativeInput` |
| 2 | `fetch_fundamentals_snapshot([])` | `MarketsInput.fundamentals` |
| 3 | `fetch_vol_snapshot()` | `MarketsInput.vol` |
| 4 | `RegimeInput(as_of, region)` | 仅复制日期与区域，**不附带上述任一步骤的数据** |

`data_plane_notes` 记录 ingest、fundamentals 行数、vol 备注（`data_plane.py:31-52`），但 notes 不进入 `RegimeInput`。

### 1.2 分析层 — 三个 LLM Agent

| 运行时类 | 模块 | `analyze()` 签名 | 报告类型 |
|----------|------|------------------|----------|
| `RegimeAgent` | `agents/regime_agent.py:42-57` | `(RegimeInput) -> RegimeReport` | `RegimeReport` |
| `NarrativeAgent` | `agents/narrative_agent.py:37-91` | `(NarrativeInput) -> NarrativeReport` | `NarrativeReport` |
| `MarketsAgent` | `agents/markets_agent.py:41-62` | `(MarketsInput) -> MarketsReport` | `MarketsReport` |

`ThemeOrchestrator`（`orchestrator.py:24-97`）在 Data Plane 之后用 `ThreadPoolExecutor(max_workers=3)` 并行提交三个 `analyze()`（`orchestrator.py:60-68`）。

### 1.3 合成层 — BriefAssembler + enrich

| 组件 | 模块 | 是否 LLM |
|------|------|----------|
| `assemble()` | `brief_assembler.py:114-223` | 否 |
| `_enrich_brief()` | `orchestrator.py:99-154` | 否 |

`assemble()` 将三份报告聚类为 `FinalTheme[]`；`_enrich_brief()` 写入日期、`data_sources`、主题快照等元数据。

---

## 2. `*Input` 契约对比（核心）

定义于 `src/investment_agent/inputs.py:13-54`。

### 2.1 `RegimeInput`（宏观 / Regime）

```python
@dataclass(frozen=True)
class RegimeInput:
    as_of: date
    region: str
```

- 文档字符串：`Macro/regime lens only — no news, fundamentals, or vol.`（`inputs.py:14-18`）
- 构造位置：`data_plane.py:54` — `RegimeInput(as_of=as_of, region=region)`
- Agent 使用：`regime_agent.py:46-57` — user prompt 仅展开 `inp.as_of`、`inp.region`；无 `context_block`、无 `to_prompt_block()` 类数据块
- Checkpoint 序列化：`checkpoint.py:153` — `regime_input` 仅存 `as_of` + `region` 两个 ISO/字符串字段

**事实归纳：** `RegimeInput` 存在且被传入 `RegimeAgent.analyze()`，但它是三个 `*Input` 中字段最少的一个；**不包含 Data Plane 拉取的任何外部市场或新闻数据**。

### 2.2 `NarrativeInput`

| 字段 | 来源 |
|------|------|
| `as_of`, `region` | `data_plane.py:55-57` |
| `retrieval_query` | `build_news_retrieval_query` |
| `articles_in_corpus`, `articles_retrieved` | ingest + RAG 计数 |
| `ingest_notes` | Finnhub/TickerTick 备注 |
| `context_block` | `format_context_block(retrieved)` |
| `retrieved` | `tuple[NewsArticle, ...]` |

Agent 将 `context_block` 嵌入 LLM user prompt（`narrative_agent.py:52`）。

### 2.3 `MarketsInput`

| 字段 | 来源 |
|------|------|
| `as_of`, `region` | `data_plane.py:65-67` |
| `fundamentals` | `fetch_fundamentals_snapshot` |
| `vol` | `fetch_vol_snapshot` |

Agent 调用 `fundamentals.to_prompt_block()` 与 `vol.to_prompt_block()`（`markets_agent.py:46-47,55-57`）。

### 2.4 输入字段数量对照

| `*Input` | 标量字段 | 结构化/文本载荷 | Data Plane HTTP/yfinance |
|-----------|----------|-----------------|--------------------------|
| `RegimeInput` | 2 | 无 | 无 |
| `NarrativeInput` | 5 + `ingest_notes` | `context_block` + `retrieved` | 是（经 Data Plane） |
| `MarketsInput` | 2 | `FundamentalsSnapshot` + `VolSnapshot` | 是（经 Data Plane） |

---

## 3. Regime Agent 的实际 LLM 输入内容

`RegimeAgent` 不接收 `Settings`；区域来自 `RegimeInput.region`（由 `settings.market_region` 在 Data Plane 写入，`data_plane.py:30`）。

**System prompt：** `regime_agent.py:6-39` — 角色、五阶段生命周期、JSON schema。

**User prompt：** `regime_agent.py:47-56` — 包含：

- 分析日期（`format_date_display` / `format_date_iso`）
- `inp.region`
- 定性考量列表（rates, inflation, fiscal, USD, China/EM, geopolitics, credit, sector rotation）
- 要求返回 4–6 个 macro themes

**无结构化数值块**（对比 `MarketsAgent` 的 fundamentals/vol 块）。

**输出：** `RegimeReport`（`models.py:87-93`）— 字段名仍用 `macro_backdrop`、`dominant_regime`（非 `regime_backdrop`）。

---

## 4. 命名与层级映射（v2 运行时 → v1 消费契约）

当前存在 **三套并行命名**，运行时类名、brief 字段、assembler 内部标签不一致：

### 4.1 Agent 运行时名称

`agents/__init__.py:1-9` 导出：`RegimeAgent`, `NarrativeAgent`, `MarketsAgent`。

### 4.2 `InvestmentBrief` 字段（v1 形状保留）

`models.py:185-206`：

| Brief 字段 | v2 数据来源 |
|------------|-------------|
| `macro_view` | `brief_assembler` 从 `RegimeReport` 拼接（`brief_assembler.py:195-198`） |
| `news_view` | `NarrativeReport.news_backdrop` |
| `equity_view` | `MarketsReport.equity_view` 或 fallback |
| `quant_view` | `MarketsReport.quant_view` 或 fallback |
| `macro_themes` | `regime.themes`（`_enrich_brief`, `orchestrator.py:149`） |
| `news_themes` | `narrative.themes` |
| `equity_themes` | `markets.equity_themes` |
| `quant_themes` | `markets.quant_themes` |

### 4.3 `brief_assembler` 内部 agent 标签

`_TaggedTheme.agent` 使用字符串 **`macro` | `news` | `equity` | `quant`**（`brief_assembler.py:27,36-43`），写入 `FinalTheme.contributing_agents` / `primary_agent`（`brief_assembler.py:149-150`）。

### 4.4 Streamlit 显示映射

`streamlit_app.py:64-69` — `AGENT_LABELS` 将 brief 的 `macro` 键显示为 "Regime"，`news` 显示为 "Narrative"，等。

预合并主题区仍为 **4 列**（macro / news / equity / quant），对应 3 个运行时 Agent 的 4 个主题列表（Markets 拆成 equity + quant 两列）（`streamlit_app.py:275-285`）。

### 4.5 模型类型重复

`models.py` 同时定义：

| v2（pipeline 使用） | v1（保留，无 agent 写入） | 结构关系 |
|---------------------|---------------------------|----------|
| `RegimeReport` `87-93` | `MacroReport` `80-84` | 字段相同 |
| `NarrativeReport` `96-108` | `NewsReport` `138-148` | 字段相同 |
| `MarketsReport` `111-122` | `EquityReport` + `QuantReport` `125-135` | Markets 合并二者 |

---

## 5. Data Plane 与 Regime 的结构性关系

```
build_data_plane(settings)
    │
    ├─► fetch news ──────────────► NarrativeInput (full payload)
    ├─► fetch fundamentals ──────► MarketsInput.fundamentals
    ├─► fetch vol ───────────────► MarketsInput.vol
    │
    └─► RegimeInput(as_of, region)   ◄── 不读取上述 fetch 结果
              │
              ▼
        RegimeAgent.analyze()  ──► 纯 LLM（无外部数据块）
```

Orchestrator 将 `plane.regime_input` 传入 Regime（`orchestrator.py:64`），与 narrative/markets 输入来自同一 `DataPlaneSnapshot`（`inputs.py:45-54`），但 **Regime 切片与 Data Plane 的数据获取步骤在代码上无数据依赖边**。

README 明确记录：`Regime uses date + region only`（`README.md:100`）；`Regime agent does not use FRED/Bloomberg APIs`（`README.md:276`）。

---

## 6. 与 v1 宏观 Agent 的对比（历史行为，供对照）

`research/three-domain-agents-design.md` 记录 v1 `MacroEconomist` 同样为 **LLM only、无 live macro API**（设计文档 `three-domain-agents-design.md:80` 要求 R6 保持等价行为）。

v1 差异（已不在代码树中）：

- v1：`MacroEconomist` 从 `Settings` 读 `market_region`；v2：从 `RegimeInput.region` 读
- v1：`QuantAnalyst` 曾接收 `macro.dominant_regime` 字符串（设计文档 `three-domain-agents-design.md:63`）；v2：该跨 Agent 路径已移除（`orchestrator.py` 无 `dominant_regime` 传递）

v2 的 `RegimeInput` 是 v1「仅日期+区域进 prompt」行为的显式 dataclass 化，而非新增宏观数据输入。

---

## 7. 流水线模块职责一览

| 路径 | 职责 |
|------|------|
| `orchestrator.py` | 调度 Data Plane → 并行三 Agent → assemble → enrich |
| `data_plane.py` | 外部数据拉取；构造三个 `*Input` |
| `inputs.py` | `*Input` / `DataPlaneSnapshot` 类型定义 |
| `agents/regime_agent.py` | Regime LLM |
| `agents/narrative_agent.py` | Narrative LLM + citation 回填 |
| `agents/markets_agent.py` | Markets LLM（equity + quant 单次调用） |
| `brief_assembler.py` | `theme_key()` 聚类、打分、视图字符串 |
| `checkpoint.py` | `data_plane` / `regime` / `narrative` / `markets` 步骤缓存 |
| `models.py` | Pydantic 报告 + `InvestmentBrief` |
| `brief_compat.py` | 加载旧 JSON、安全字段访问 |
| `news/` | ingest + RAG（仅 Data Plane / Narrative 路径使用） |
| `data/` + `market_data.py` | 基本面 + vol（仅 Markets 路径使用） |

`Settings.pipeline_version`（`config.py:32,84`）从环境变量加载；`checkpoint.PIPELINE_VERSION = 2`（`checkpoint.py:26`）用于 resume 元数据；**orchestrator 不读取 `settings.pipeline_version` 做分支**。

---

## 8. 端到端数据流（含 Regime 空数据边）

```
Settings.from_env()
       │
       ▼
build_data_plane()
  news, fundamentals, vol  ──┬──► NarrativeInput
                               ├──► MarketsInput
                               └──► RegimeInput { as_of, region only }
       │
       ▼
ThreadPoolExecutor (parallel)
  RegimeAgent(RegimeInput)     → RegimeReport  → macro_* fields
  NarrativeAgent(NarrativeInput) → NarrativeReport → news_* fields
  MarketsAgent(MarketsInput)   → MarketsReport   → equity_* + quant_* fields
       │
       ▼
assemble()  tags: macro|news|equity|quant  →  FinalTheme[]
       │
       ▼
_enrich_brief()  →  InvestmentBrief  →  reports/latest.json
```

**LLM 调用次数：** 3（`orchestrator.py:60-68`）。

---

## 9. 测试与文档中的 Regime 输入

- `tests/test_brief_assembler.py:30-35` — 测试用 `RegimeReport` 构造数据，**不经过 `RegimeInput` 或 `RegimeAgent`**
- `research/codebase-overview.md` — 全库总览（含 RegimeInput 两字段说明）
- `research/three-domain-agents-design.md` — v1→v2 设计计划（状态为 Draft plan）；其中 `regime_slice → RegimeInput { as_of, region }`（`three-domain-agents-design.md:124`）与现实现一致

---

## 10. 交叉引用索引

| 问题 | 代码事实 | 引用 |
|------|----------|------|
| Regime 有没有 `*Input` 类型？ | 有，`RegimeInput` | `inputs.py:13-18` |
| Regime 输入包含哪些字段？ | `as_of`, `region` | `inputs.py:17-18` |
| Data Plane 是否为 Regime 拉数据？ | 否；仅构造两字段 | `data_plane.py:54` |
| Regime LLM prompt 含何数据？ | 日期、区域、定性指引 | `regime_agent.py:47-56` |
| Brief 为何仍叫 macro？ | v1 兼容字段名 | `models.py:192,203`；`orchestrator.py:149` |
| 几个运行时 Agent vs 几列 UI？ | 3 Agent，4 列主题快照 | `streamlit_app.py:275-285` |
| Markets 是否拆成两个逻辑 Agent？ | 单 `MarketsAgent`，双主题列表 | `markets_agent.py:8-10`；`models.py:119-120` |
