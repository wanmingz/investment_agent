"""LLM and API errors with actionable messages."""

from __future__ import annotations


class QuotaExhaustedError(RuntimeError):
    """Gemini/OpenAI quota or rate limit (HTTP 429)."""

    def __init__(
        self,
        message: str,
        *,
        provider: str = "",
        model: str = "",
        schema_name: str = "",
        retry_after_seconds: float | None = None,
        daily_limit: bool = False,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.schema_name = schema_name
        self.retry_after_seconds = retry_after_seconds
        self.daily_limit = daily_limit

    def user_hint(self) -> str:
        lines = [str(self)]
        if self.daily_limit:
            lines.append(
                "Free-tier daily request cap hit. Each full run uses ~5 LLM calls "
                "(macro, news, equity, quant, CIO). Wait until quota resets (UTC), "
                "use another API key, switch LLM_PROVIDER/model, or enable "
                "RESUME_CHECKPOINT=1 to continue from the last saved step."
            )
        elif self.retry_after_seconds:
            lines.append(
                f"Short-term rate limit — retry after ~{int(self.retry_after_seconds)}s."
            )
        lines.append("In the sidebar: use **Load last result** or **Resume from checkpoint**.")
        return "\n\n".join(lines)
