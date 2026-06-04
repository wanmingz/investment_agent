import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_DEFAULT_MODEL = "gemini-2.0-flash"


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    model: str
    market_region: str
    provider: str  # "gemini" | "openai"

    @classmethod
    def from_env(cls) -> "Settings":
        provider = os.getenv("LLM_PROVIDER", "").strip().lower()
        gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()

        if provider == "gemini" or (gemini_key and provider != "openai"):
            if not gemini_key:
                raise ValueError(
                    "LLM_PROVIDER=gemini but GEMINI_API_KEY is not set.\n"
                    "Add your key from https://aistudio.google.com/apikey to .env"
                )
            return cls(
                api_key=gemini_key,
                base_url=os.getenv("OPENAI_BASE_URL", GEMINI_OPENAI_BASE_URL),
                model=os.getenv("GEMINI_MODEL", os.getenv("OPENAI_MODEL", GEMINI_DEFAULT_MODEL)),
                market_region=os.getenv("MARKET_REGION", "global"),
                provider="gemini",
            )

        if openai_key:
            return cls(
                api_key=openai_key,
                base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                model=os.getenv("OPENAI_MODEL", "gpt-4o"),
                market_region=os.getenv("MARKET_REGION", "global"),
                provider="openai",
            )

        if gemini_key:
            return cls(
                api_key=gemini_key,
                base_url=os.getenv("OPENAI_BASE_URL", GEMINI_OPENAI_BASE_URL),
                model=os.getenv("GEMINI_MODEL", GEMINI_DEFAULT_MODEL),
                market_region=os.getenv("MARKET_REGION", "global"),
                provider="gemini",
            )

        raise ValueError(
            "No API key found. Copy .env.example to .env and set one of:\n"
            "  GEMINI_API_KEY=...   (recommended, Google AI Studio)\n"
            "  OPENAI_API_KEY=...   (OpenAI or compatible API)"
        )
