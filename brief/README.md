# Published investment briefs

Reports in this folder are updated automatically by the [**Weekly theme brief**](../.github/workflows/weekly-brief.yml) GitHub Action (Mondays 06:00 UTC, or manual run).

| Report | Description |
|--------|-------------|
| [**latest.md**](./latest.md) | Most recent analysis — open on GitHub for formatted reading |
| [**latest.json**](./latest.json) | Same brief as JSON — loaded by the Streamlit dashboard when `reports/` is absent (e.g. Streamlit Community Cloud) |
| [**portfolio_latest.json**](./portfolio_latest.json) | Read-only **My portfolio** snapshot for Cloud (publish with `invest-portfolio publish`) |
| [**runs/**](./runs/) | Timestamped Markdown archives (`YYYY-MM-DD_HHMMSS.md`) |

Local runs still write `reports/latest.json` (gitignored). The dashboard prefers that path, then falls back to `brief/latest.json`.

Portfolio: local `reports/portfolio.db` is gitignored. When it has no trades, Streamlit loads `portfolio_latest.json` as a read-only view for friends.
