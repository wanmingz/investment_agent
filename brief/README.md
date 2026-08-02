# Published investment briefs

Reports in this folder are updated automatically by the [**Weekly theme brief**](../.github/workflows/weekly-brief.yml) GitHub Action (Mondays 06:00 UTC, or manual run).

| Report | Description |
|--------|-------------|
| [**latest.md**](./latest.md) | Most recent analysis — open on GitHub for formatted reading |
| [**latest.json**](./latest.json) | Same brief as JSON — loaded by the Streamlit dashboard when `reports/` is absent (e.g. Streamlit Community Cloud) |
| [**runs/**](./runs/) | Timestamped Markdown archives (`YYYY-MM-DD_HHMMSS.md`) |

Local runs still write `reports/latest.json` (gitignored). The dashboard prefers that path, then falls back to `brief/latest.json`.
