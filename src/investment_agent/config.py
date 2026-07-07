import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_DEFAULT_MODEL = "gemini-2.0-flash"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_DEFAULT_MODEL = "llama-3.3-70b-versatile"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_FREE_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
OPENAI_DEFAULT_BASE = "https://api.openai.com/v1"
OPENAI_DEFAULT_MODEL = "gpt-4o"


def env_int(name: str, default: int) -> int:
    """Parse int env var; empty or invalid values use *default* (GitHub Actions secrets)."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def env_str(name: str, default: str) -> str:
    """Non-empty env var or *default* (treats blank secrets as unset)."""
    raw = os.getenv(name, "").strip()
    return raw or default


def _int_env(name: str, default: int) -> int:
    return env_int(name, default)


def _bool_env(name: str) -> bool | None:
    raw = os.getenv(name, "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return None


def _is_groq(base_url: str) -> bool:
    return "groq.com" in base_url.lower()


def _is_openrouter_free(base_url: str, model: str) -> bool:
    return "openrouter.ai" in base_url.lower() and ":free" in model.lower()


def _llm_parallel_agents(base_url: str, model: str) -> bool:
    override = _bool_env("LLM_PARALLEL_AGENTS")
    if override is not None:
        return override
    if _is_groq(base_url):
        return False
    # OpenRouter free models: ~20 RPM; parallel 3-agent burst often 429s.
    if _is_openrouter_free(base_url, model):
        return False
    return True


def _llm_agent_delay_seconds(base_url: str, model: str) -> float:
    raw = os.getenv("LLM_AGENT_DELAY_SECONDS", "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    if _is_openrouter_free(base_url, model):
        return 5.0
    return 0.0


def _resolve_openai_compat(api_key: str) -> tuple[str, str]:
    """Infer Groq/OpenRouter base URL + model from key prefix when env is unset."""
    base = env_str("OPENAI_BASE_URL", "")
    model = env_str("OPENAI_MODEL", "")
    if api_key.startswith("gsk_"):
        return base or GROQ_BASE_URL, model or GROQ_DEFAULT_MODEL
    if api_key.startswith("sk-or-"):
        return base or OPENROUTER_BASE_URL, model or OPENROUTER_FREE_MODEL
    return base or OPENAI_DEFAULT_BASE, model or OPENAI_DEFAULT_MODEL


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    model: str
    market_region: str
    provider: str  # "gemini" | "openai"
    finnhub_api_key: str = ""
    news_max_articles: int = 40
    rag_top_k: int = 12
    rag_summary_max_chars: int = 500
    rag_context_max_chars: int = 10_000
    pipeline_version: int = 2
    llm_parallel_agents: bool = True
    llm_agent_delay_seconds: float = 0.0

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
            return cls._with_news(
                api_key=gemini_key,
                base_url=env_str("OPENAI_BASE_URL", GEMINI_OPENAI_BASE_URL),
                model=env_str("GEMINI_MODEL", env_str("OPENAI_MODEL", GEMINI_DEFAULT_MODEL)),
                market_region=env_str("MARKET_REGION", "global"),
                provider="gemini",
            )

        if openai_key:
            base_url, model = _resolve_openai_compat(openai_key)
            return cls._with_news(
                api_key=openai_key,
                base_url=base_url,
                model=model,
                market_region=env_str("MARKET_REGION", "global"),
                provider="openai",
            )

        if gemini_key:
            return cls._with_news(
                api_key=gemini_key,
                base_url=env_str("OPENAI_BASE_URL", GEMINI_OPENAI_BASE_URL),
                model=env_str("GEMINI_MODEL", GEMINI_DEFAULT_MODEL),
                market_region=env_str("MARKET_REGION", "global"),
                provider="gemini",
            )

        raise ValueError(
            "No API key found. Copy .env.example to .env and set one of:\n"
            "  GEMINI_API_KEY=...   (recommended, Google AI Studio)\n"
            "  OPENAI_API_KEY=...   (OpenAI or compatible API)"
        )

    @classmethod
    def _with_news(cls, **kwargs) -> "Settings":
        base_url = str(kwargs.get("base_url", ""))
        model = str(kwargs.get("model", ""))
        groq = _is_groq(base_url)
        return cls(
            finnhub_api_key=os.getenv("FINNHUB_API_KEY", "").strip(),
            news_max_articles=_int_env("NEWS_MAX_ARTICLES", 25 if groq else 80),
            rag_top_k=_int_env("RAG_TOP_K", 5 if groq else 24),
            rag_summary_max_chars=_int_env("RAG_SUMMARY_MAX_CHARS", 180 if groq else 500),
            rag_context_max_chars=_int_env("RAG_CONTEXT_MAX_CHARS", 3_000 if groq else 10_000),
            pipeline_version=_int_env("PIPELINE_VERSION", 2),
            llm_parallel_agents=_llm_parallel_agents(base_url, model),
            llm_agent_delay_seconds=_llm_agent_delay_seconds(base_url, model),
            **kwargs,
        )

    @property
    def is_groq(self) -> bool:
        return _is_groq(self.base_url)

    @property
    def is_openrouter_free(self) -> bool:
        return _is_openrouter_free(self.base_url, self.model)
