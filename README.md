# Investment Agent — 多 Agent 投资主题分析

三个专业 Agent 协作，输出**当前值得投资的主题**，并标注生命周期阶段：**早期 / 中期 / 晚期**。

| Agent | 角色 | 职责 |
|-------|------|------|
| **Agent 1** | 宏观经济学家 (Macro Economist) | 利率、通胀、政策、地缘、跨资产信号 → 宏观视角主题与阶段 |
| **Agent 2** | 股票研究员 (Equity Research Analyst) | 估值、盈利修正、风格与板块 → 股票基本面视角验证/修正阶段 |
| **Agent 3** | 量化分析师 (Quant Analyst) | 波动率、VIX、板块 realized vol → 风险与时机视角阶段判断 |

CIO 合成层汇总三方观点，给出最终阶段、共识度与可投资性评分。

## 阶段定义

| 阶段 | 英文 | 含义 |
|------|------|------|
| 早期 | `early` | 主题刚形成，宏观/盈利/波动尚未充分定价，适合布局 |
| 中期 | `mid` | 趋势确认、盈利与资金流入，主升或兑现期 |
| 晚期 | `late` | 拥挤、估值极端或波动飙升，过热或应退出观察 |

## 快速开始

```bash
cd investment_agent
python -m venv .venv
source .venv/bin/activate
pip install -e .

cp .env.example .env
# 编辑 .env，填入 GEMINI_API_KEY（推荐）或 OPENAI_API_KEY
```

### 使用 Gemini

1. 打开 [Google AI Studio](https://aistudio.google.com/apikey) 创建 API Key  
2. 在 `.env` 中设置：

```bash
LLM_PROVIDER=gemini
GEMINI_API_KEY=你的密钥
GEMINI_MODEL=gemini-2.0-flash
```

程序通过 Gemini 的 [OpenAI 兼容接口](https://ai.google.dev/gemini-api/docs/openai) 调用模型。

运行：

```bash
python main.py
# 或
invest-themes

# JSON 输出
python main.py --json

# 指定市场区域
python main.py --region China

# 保存 JSON 供前端加载
python main.py -o reports/latest.json
```

### Web 前端（Streamlit）

```bash
streamlit run streamlit_app.py
# 或
invest-dashboard
```

浏览器打开后：
1. 侧边栏选择市场区域，点击 **「开始分析」**
2. 或点击 **「加载上次结果」** 查看 `reports/latest.json`
```

## 环境变量

| 变量 | 说明 |
|------|------|
| `GEMINI_API_KEY` | Gemini 密钥（与 `LLM_PROVIDER=gemini` 配合） |
| `GEMINI_MODEL` | 可选，默认 `gemini-2.0-flash` |
| `LLM_PROVIDER` | `gemini` 或 `openai` |
| `OPENAI_API_KEY` | OpenAI 或其它兼容服务密钥 |
| `OPENAI_BASE_URL` | 可选；Gemini 默认已指向 Google 兼容端点 |
| `MARKET_REGION` | 可选，`global` / `US` / `China` 等 |

## 架构

```
main.py / CLI
    └── ThemeOrchestrator
            ├── Agent 1: MacroEconomist      → MacroReport
            ├── Agent 2: EquityResearchAnalyst → EquityReport (读 macro)
            ├── Agent 3: QuantAnalyst        → QuantReport (读 macro+equity + yfinance vol)
            └── CIO Synthesis                → InvestmentBrief
```

Agent 3 会尝试通过 `yfinance` 拉取 VIX 与板块 ETF 的 20 日年化波动率，作为量化判断的硬数据输入。

## 免责声明

输出仅供研究参考，不构成投资建议。
