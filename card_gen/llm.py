"""Обращение к LLM. Остальной код зависит только от протокола LLMClient,
поэтому в тестах модель подменяется заглушкой, а провайдера можно сменить,
написав ещё один класс с методом complete()."""

from __future__ import annotations

import logging
from typing import Protocol

import anthropic

from .config import Settings

log = logging.getLogger(__name__)

MAX_TOKENS = 16000
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(RuntimeError):
    """Ошибка на стороне модели или API. Текст предназначен для пользователя."""


class LLMClient(Protocol):
    model: str

    def complete(self, system: str, user: str, schema: dict) -> str:
        """Возвращает текст ответа модели (JSON по схеме schema)."""
        ...


class AnthropicClient:
    """Claude через официальный SDK со structured outputs (output_config.format)."""

    def __init__(self, settings: Settings, sdk_client: anthropic.Anthropic | None = None):
        self.settings = settings
        self.model = settings.model
        self.fix_attempts = settings.fix_attempts
        self._client = sdk_client or anthropic.Anthropic(
            api_key=settings.api_key,
            timeout=float(settings.timeout),
            max_retries=settings.max_retries,  # SDK сам повторяет 429, 5xx и обрывы связи
        )

    def _send(self, system: str, user: str, schema: dict):
        params = dict(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={
                "effort": self.settings.effort,
                "format": {"type": "json_schema", "schema": schema},
            },
        )
        if self.settings.fallbacks != "off":
            # При отказе модели (stop_reason=refusal) API само повторит запрос
            # на рекомендованной резервной модели
            return self._client.beta.messages.create(**params, betas=[FALLBACK_BETA], fallbacks=self.settings.fallbacks)
        return self._client.messages.create(**params)

    def complete(self, system: str, user: str, schema: dict) -> str:
        try:
            response = self._send(system, user, schema)
        except anthropic.AuthenticationError as exc:
            raise LLMError("API-ключ не принят (401). Проверьте ANTHROPIC_API_KEY") from exc
        except anthropic.PermissionDeniedError as exc:
            raise LLMError("У ключа нет доступа к этой модели или функции (403)") from exc
        except anthropic.NotFoundError as exc:
            raise LLMError(f"Модель {self.model!r} не найдена (404). Проверьте LLM_MODEL") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("Превышен лимит запросов к API (429). Повторите через минуту") from exc
        except anthropic.BadRequestError as exc:
            raise LLMError(f"API отклонил запрос (400): {exc.message}") from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                raise LLMError(f"Сервис LLM временно недоступен ({exc.status_code}). Повторите позже") from exc
            raise LLMError(f"Ошибка API ({exc.status_code}): {exc.message}") from exc
        except anthropic.APITimeoutError as exc:
            raise LLMError(
                f"Модель не ответила за {self.settings.timeout} с. Повторите или увеличьте LLM_TIMEOUT"
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("Нет связи с API. Проверьте интернет и прокси") from exc

        log.info("request_id=%s stop_reason=%s", getattr(response, "_request_id", None), response.stop_reason)
        if response.stop_reason == "refusal":
            raise LLMError("Модель отказалась отвечать на этот запрос. Проверьте входные данные")
        if response.stop_reason == "max_tokens":
            raise LLMError("Ответ модели обрезан по лимиту длины. Сократите описание во входных данных")

        text = "".join(block.text for block in response.content if block.type == "text")
        if not text.strip():
            raise LLMError("Модель вернула пустой ответ")
        return text
