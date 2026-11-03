"""Веб-форма и HTTP API.

Запуск: uvicorn card_gen.web:app --reload  (или python -m card_gen.web)
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Callable

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

from .checks import InsufficientDataError, check_input
from .config import ConfigError, Settings
from .generator import generate_card
from .input_loader import InputError, load_product
from .llm import AnthropicClient, LLMClient, LLMError
from .render import render_markdown

STATIC = Path(__file__).parent / "static"
EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

app = FastAPI(title="Черновики карточек товаров")


@lru_cache(maxsize=1)
def _default_client() -> AnthropicClient:
    return AnthropicClient(Settings.from_env())


def get_client_factory() -> Callable[[], LLMClient]:
    """Зависимость FastAPI. Клиент создаётся лениво внутри обработчика, чтобы
    ошибки входных данных возвращались раньше, чем проверка API-ключа.
    В тестах подменяется через app.dependency_overrides."""
    return _default_client


def _error(status: int, message: str, issues: list | None = None) -> JSONResponse:
    body = {"error": message}
    if issues is not None:
        body["issues"] = [i.model_dump() for i in issues]
    return JSONResponse(body, status_code=status)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/examples")
def examples() -> dict:
    """Входные JSON из папки examples, чтобы в форме можно было подставить пример."""
    items = {}
    for path in sorted(EXAMPLES.glob("*.json")):
        try:
            items[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return items


@app.post("/api/check")
async def check(request: Request):
    try:
        product = load_product(await request.body())
        issues = check_input(product)
    except InputError as exc:
        return _error(400, str(exc))
    except InsufficientDataError as exc:
        return _error(422, "Недостаточно данных для карточки", exc.issues)
    return {"issues": [i.model_dump() for i in issues]}


@app.post("/api/card")
async def card(request: Request, client_factory: Callable[[], LLMClient] = Depends(get_client_factory)):
    try:
        product = load_product(await request.body())
        # Сначала проверяем вход: при нехватке данных ключ API даже не нужен
        check_input(product)
        client = client_factory()
        # Запрос к модели блокирующий: выполняем его в пуле потоков
        result = await run_in_threadpool(
            generate_card, product, client, fix_attempts=getattr(client, "fix_attempts", 1)
        )
    except InputError as exc:
        return _error(400, str(exc))
    except InsufficientDataError as exc:
        return _error(422, "Недостаточно данных для карточки", exc.issues)
    except ConfigError as exc:
        return _error(503, str(exc))
    except LLMError as exc:
        return _error(502, str(exc))
    return {"card": result.model_dump(), "markdown": render_markdown(result)}


def main() -> None:
    import uvicorn

    uvicorn.run("card_gen.web:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
