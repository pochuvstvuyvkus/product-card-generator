"""Настройки из переменных окружения и файла .env (в git не попадает)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_MODEL = "claude-sonnet-5-5"
EFFORT_LEVELS = ("low", "medium", "high")


class ConfigError(RuntimeError):
    """Не хватает настроек для запуска (обычно нет API-ключа)."""


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} должен быть целым числом, сейчас: {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    api_key: str
    model: str = DEFAULT_MODEL
    effort: str = "medium"
    timeout: int = 120
    max_retries: int = 2
    fix_attempts: int = 1
    fallbacks: str = "default"

    @classmethod
    def from_env(cls, require_key: bool = True) -> "Settings":
        load_dotenv(Path.cwd() / ".env")  # переменные окружения важнее .env
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if require_key and not api_key:
            raise ConfigError(
                "Не задан ANTHROPIC_API_KEY. Скопируйте .env.example в .env и впишите ключ "
                "или выполните export ANTHROPIC_API_KEY=..."
            )
        effort = os.getenv("LLM_EFFORT", "medium").strip() or "medium"
        if effort not in EFFORT_LEVELS:
            raise ConfigError(f"LLM_EFFORT должен быть одним из {', '.join(EFFORT_LEVELS)}, сейчас: {effort!r}")
        return cls(
            api_key=api_key,
            model=os.getenv("LLM_MODEL", "").strip() or DEFAULT_MODEL,
            effort=effort,
            timeout=_int_env("LLM_TIMEOUT", 120),
            max_retries=_int_env("LLM_MAX_RETRIES", 2),
            fix_attempts=max(0, _int_env("LLM_FIX_ATTEMPTS", 1)),
            fallbacks=os.getenv("LLM_FALLBACKS", "default").strip() or "default",
        )
