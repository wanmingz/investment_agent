import json
import os
import re
import time
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from investment_agent.config import Settings

T = TypeVar("T", bound=BaseModel)


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
                "Free-tier daily request cap hit. Each full run uses ~3 LLM calls "
                "(regime, narrative, markets). Wait until quota resets (UTC), "
                "use another API key, switch LLM_PROVIDER/model, or enable "
                "RESUME_CHECKPOINT=1 to continue from the last saved step."
            )
        elif self.retry_after_seconds:
            lines.append(
                f"Short-term rate limit — retry after ~{int(self.retry_after_seconds)}s."
            )
        else:
            lines.append(
                "Short-term rate limit — wait a minute and retry, or enable "
                "RESUME_CHECKPOINT=1 to skip completed agents."
            )
        if "openrouter" in (self.provider or "").lower() or ":free" in (self.model or ""):
            lines.append(
                "OpenRouter free models are ~50 requests/day and ~20/min. "
                "Agents run sequentially by default; set LLM_PARALLEL_AGENTS=1 to override."
            )
        lines.append("In the sidebar: use **Load last result** or **Resume from checkpoint**.")
        return "\n\n".join(lines)

_JSON_FENCE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL | re.IGNORECASE)
_RETRY_SECONDS_RE = re.compile(r"retry in (\d+(?:\.\d+)?)\s*s", re.IGNORECASE)
_DAILY_QUOTA_RE = re.compile(
    r"PerDay|per day|free_tier_requests|GenerateRequestsPerDay|"
    r"free-models-per-day|per-day|daily.?limit|requests per day",
    re.IGNORECASE,
)


def _extract_json(text: str) -> dict:
    text = text.strip()
    match = _JSON_FENCE.match(text)
    if match:
        text = match.group(1).strip()
    return json.loads(text)


def _parse_429(exc: Exception) -> tuple[bool, float | None]:
    """Return (is_daily_limit, retry_after_seconds)."""
    text = str(exc)
    daily = bool(_DAILY_QUOTA_RE.search(text))
    retry_after: float | None = None
    m = _RETRY_SECONDS_RE.search(text)
    if m:
        try:
            retry_after = float(m.group(1))
        except ValueError:
            retry_after = None
    if hasattr(exc, "response") and exc.response is not None:
        try:
            body = exc.response.json()
            err = body.get("error", body)
            if isinstance(err, dict):
                msg = str(err.get("message", ""))
                code = str(err.get("code", ""))
                metadata = err.get("metadata", {}) or {}
                if isinstance(metadata, dict):
                    msg = f"{msg} {metadata}"
                blob = f"{msg} {code} {text}"
                if _DAILY_QUOTA_RE.search(blob):
                    daily = True
                if retry_after is None:
                    ra = err.get("retry_after")
                    if isinstance(ra, (int, float)) and ra > 0:
                        retry_after = float(ra)
                    elif isinstance(metadata, dict):
                        ra_meta = metadata.get("retry_after")
                        if isinstance(ra_meta, (int, float)) and ra_meta > 0:
                            retry_after = float(ra_meta)
            details = (
                body.get("error", {}).get("details", [])
                if isinstance(body.get("error"), dict)
                else []
            )
            for d in details:
                if d.get("@type", "").endswith("RetryInfo"):
                    delay = d.get("retryDelay", "")
                    if isinstance(delay, str) and delay.endswith("s"):
                        retry_after = float(delay[:-1])
        except Exception:
            pass
    return daily, retry_after


def _is_context_too_large(exc: Exception) -> bool:
    if getattr(exc, "status_code", None) == 413:
        return True
    text = str(exc).lower()
    return (
        "413" in text
        or "request too large" in text
        or ("tokens per minute" in text and "requested" in text)
        or ("tpm" in text and "limit" in text)
    )


def _compact_schema(schema: type[BaseModel]) -> str:
    """Smaller JSON schema for token-limited providers (drops descriptions/titles)."""

    def _strip(node: object) -> None:
        if isinstance(node, dict):
            node.pop("description", None)
            node.pop("title", None)
            node.pop("default", None)
            for value in node.values():
                _strip(value)
        elif isinstance(node, list):
            for item in node:
                _strip(item)

    data = schema.model_json_schema()
    _strip(data)
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _schema_hint(schema: type[BaseModel], *, compact: bool) -> str:
    if compact:
        return _compact_schema(schema)
    return json.dumps(schema.model_json_schema(), ensure_ascii=False)


def _context_too_large_hint(schema_name: str) -> str:
    return (
        f"LLM prompt too large while calling {schema_name}.\n\n"
        "Groq on-demand caps ~12k tokens per request. Try in `.env`:\n"
        "  RAG_TOP_K=4\n"
        "  RAG_SUMMARY_MAX_CHARS=150\n"
        "  RAG_CONTEXT_MAX_CHARS=2500\n"
        "  NEWS_MAX_ARTICLES=20\n\n"
        "Clear checkpoint (sidebar) or set RESUME_CHECKPOINT=0, restart, run again."
    )


def _is_rate_limit_error(exc: Exception) -> bool:
    if getattr(exc, "status_code", None) == 429:
        return True
    text = str(exc).lower()
    return (
        "429" in text
        or "resource_exhausted" in text
        or "quota" in text
        or "rate limit" in text
        or "too many requests" in text
    )


def _max_429_retries(settings: Settings) -> int:
    raw = os.getenv("LLM_MAX_RETRIES_ON_429", "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    if settings.is_openrouter_free:
        return 4
    return 2


class LLMClient:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = OpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
        )

    def structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        temperature: float = 0.3,
    ) -> T:
        compact = self._settings.is_groq or os.getenv("LLM_COMPACT_SCHEMA", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        schema_hint = _schema_hint(schema, compact=compact)
        system_full = (
            f"{system}\n\n"
            "Respond with a single valid JSON object only (no markdown).\n"
            "All string fields must be English (US).\n"
            f"JSON schema:\n{schema_hint}"
        )

        max_retries = _max_429_retries(self._settings)
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            rate_limited = False
            for use_json_mode in (True, False):
                try:
                    kwargs: dict = {
                        "model": self._settings.model,
                        "temperature": temperature,
                        "messages": [
                            {"role": "system", "content": system_full},
                            {"role": "user", "content": user},
                        ],
                    }
                    if use_json_mode:
                        kwargs["response_format"] = {"type": "json_object"}

                    response = self._client.chat.completions.create(**kwargs)
                    raw = response.choices[0].message.content or "{}"
                    data = _extract_json(raw)
                    return schema.model_validate(data)
                except (json.JSONDecodeError, ValidationError) as exc:
                    last_error = exc
                    continue
                except Exception as exc:
                    last_error = exc
                    if _is_context_too_large(exc):
                        raise RuntimeError(_context_too_large_hint(schema.__name__)) from exc
                    if _is_rate_limit_error(exc):
                        rate_limited = True
                        daily, retry_after = _parse_429(exc)
                        if daily or attempt >= max_retries:
                            raise QuotaExhaustedError(
                                f"API quota/rate limit while calling {schema.__name__} "
                                f"({self._settings.provider}/{self._settings.model}).",
                                provider=self._settings.provider,
                                model=self._settings.model,
                                schema_name=schema.__name__,
                                retry_after_seconds=retry_after,
                                daily_limit=daily,
                            ) from exc
                        wait = retry_after if retry_after and retry_after > 0 else (
                            15.0 if self._settings.is_openrouter_free else 50.0
                        )
                        time.sleep(min(wait, 120.0))
                        break
                    continue
            if not rate_limited:
                break

        if last_error and _is_context_too_large(last_error):
            raise RuntimeError(_context_too_large_hint(schema.__name__)) from last_error
        if last_error and _is_rate_limit_error(last_error):
            daily, retry_after = _parse_429(last_error)
            raise QuotaExhaustedError(
                f"API quota/rate limit while calling {schema.__name__} "
                f"({self._settings.provider}/{self._settings.model}).",
                provider=self._settings.provider,
                model=self._settings.model,
                schema_name=schema.__name__,
                retry_after_seconds=retry_after,
                daily_limit=daily,
            ) from last_error

        raise RuntimeError(
            f"LLM response could not be parsed as {schema.__name__} "
            f"(provider={self._settings.provider}): {last_error}"
        ) from last_error
