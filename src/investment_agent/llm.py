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
        lines.append("In the sidebar: use **Load last result** or **Resume from checkpoint**.")
        return "\n\n".join(lines)

_JSON_FENCE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL | re.IGNORECASE)
_RETRY_SECONDS_RE = re.compile(r"retry in (\d+(?:\.\d+)?)\s*s", re.IGNORECASE)
_DAILY_QUOTA_RE = re.compile(
    r"PerDay|per day|free_tier_requests|GenerateRequestsPerDay",
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
            details = body.get("error", {}).get("details", [])
            for d in details:
                if d.get("@type", "").endswith("RetryInfo"):
                    delay = d.get("retryDelay", "")
                    if isinstance(delay, str) and delay.endswith("s"):
                        retry_after = float(delay[:-1])
        except Exception:
            pass
    return daily, retry_after


def _is_rate_limit_error(exc: Exception) -> bool:
    if getattr(exc, "status_code", None) == 429:
        return True
    text = str(exc).lower()
    return "429" in text or "resource_exhausted" in text or "quota" in text


def _max_429_retries() -> int:
    raw = os.getenv("LLM_MAX_RETRIES_ON_429", "2").strip()
    try:
        return max(0, int(raw))
    except ValueError:
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
        schema_hint = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        system_full = (
            f"{system}\n\n"
            "You MUST respond with a single valid JSON object only "
            "(no markdown fences, no commentary).\n"
            f"JSON schema:\n{schema_hint}"
        )

        max_retries = _max_429_retries()
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
                        wait = retry_after if retry_after and retry_after > 0 else 50.0
                        time.sleep(min(wait, 120.0))
                        break
                    continue
            if not rate_limited:
                break

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
