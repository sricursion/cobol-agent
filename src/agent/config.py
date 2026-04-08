"""Runtime configuration for the COBOL conversion agent."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


load_dotenv()


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from the environment."""

    openai_api_key: str | None
    openai_base_url: str | None
    openai_model: str
    app_title: str
    app_description: str
    mock_openai: bool
    max_fix_rounds: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings for the current process."""

    # Prefer explicit OpenAI keys locally; HF_TOKEN last for Spaces/inference setups
    # that only expose a single secret name.
    openai_api_key = (
        os.getenv("OPENAI_API_KEY")
        or os.getenv("API_KEY")
        or os.getenv("HF_TOKEN")
    )
    return Settings(
        openai_api_key=openai_api_key,
        openai_base_url=os.getenv("API_BASE_URL"),
        openai_model=os.getenv("MODEL_NAME") or os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        app_title=os.getenv("APP_TITLE", "COBOL Conversion Agent"),
        app_description=os.getenv(
            "APP_DESCRIPTION",
            (
                "Extract Mermaid structure from COBOL, compare COBOL and Python "
                "dependencies, and auto-fix the generated artifacts."
            ),
        ),
        mock_openai=_env_flag("MOCK_OPENAI", default=not bool(openai_api_key)),
        max_fix_rounds=max(1, int(os.getenv("MAX_FIX_ROUNDS", "1"))),
    )
