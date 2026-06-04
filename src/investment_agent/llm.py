import json
import re
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from investment_agent.config import Settings

T = TypeVar("T", bound=BaseModel)

_JSON_FENCE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL | re.IGNORECASE)


def _extract_json(text: str) -> dict:
    text = text.strip()
    match = _JSON_FENCE.match(text)
    if match:
        text = match.group(1).strip()
    return json.loads(text)


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

        last_error: Exception | None = None
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
            except (json.JSONDecodeError, ValidationError, Exception) as exc:
                last_error = exc
                continue

        raise RuntimeError(
            f"LLM response could not be parsed as {schema.__name__} "
            f"(provider={self._settings.provider}): {last_error}"
        ) from last_error
