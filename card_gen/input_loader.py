"""Разбор и нормализация входного JSON.

Все ошибки формата превращаются в InputError с понятным текстом на русском,
чтобы контент-менеджер видел, что именно исправить во входных данных.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any

from .models import ProductInput


class InputError(ValueError):
    """Входные данные нельзя разобрать."""


# Синонимы полей: так данные можно передать прямо из выгрузки фида
FIELD_ALIASES = {
    "title": "name",
    "vendor": "manufacturer",
    "brand": "manufacturer",
    "params": "specs",
    "characteristics": "specs",
    "typePrefix": "category",
    "type": "category",
    "vendorCode": "sku",
}
TEXT_FIELDS = ("name", "manufacturer", "description", "category", "url", "sku")

_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_TAG_RE = re.compile(r"</?(p|div|br|li|ul|ol|h\d|tr|table)\b[^>]*>", re.I)


def clean_text(value: str) -> str:
    """Убирает HTML-теги и лишние пробелы, сохраняя деление на абзацы."""
    if "<" in value and ">" in value:
        value = _BLOCK_TAG_RE.sub("\n", value)
        value = _TAG_RE.sub("", value)
    value = html.unescape(value).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.splitlines()]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _scalar_to_text(value: Any, where: str) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return clean_text(value)
    raise InputError(f"Поле «{where}» должно быть строкой, получено: {type(value).__name__}")


def _spec_value(value: Any, key: str) -> str:
    if isinstance(value, list):
        parts = [_scalar_to_text(v, f"specs.{key}") for v in value]
        return ", ".join(p for p in parts if p)
    if isinstance(value, dict):
        parts = [f"{k}: {_scalar_to_text(v, f'specs.{key}.{k}')}" for k, v in value.items()]
        return "; ".join(parts)
    return _scalar_to_text(value, f"specs.{key}")


def _parse_specs(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        items = list(raw.items())
    elif isinstance(raw, list):
        # Допускаем [{"name": ..., "value": ...}] и ["Ключ: значение"]
        items = []
        for i, entry in enumerate(raw):
            if isinstance(entry, dict) and "name" in entry:
                items.append((entry["name"], entry.get("value")))
            elif isinstance(entry, str) and ":" in entry:
                key, _, val = entry.partition(":")
                items.append((key, val))
            else:
                raise InputError(f'specs[{i}]: ожидается объект {{"name", "value"}} или строка «ключ: значение»')
    else:
        raise InputError('Поле «specs» должно быть объектом вида {"характеристика": "значение"}')

    specs: dict[str, str] = {}
    for key, value in items:
        name = clean_text(str(key)).rstrip(":").strip()
        if not name:
            raise InputError("В «specs» есть характеристика с пустым названием")
        specs[name] = _spec_value(value, name)
    return specs


def parse_product(data: Any) -> ProductInput:
    """Проверяет структуру уже разобранного JSON и нормализует поля."""
    if not isinstance(data, dict):
        raise InputError("Ожидается JSON-объект с полями name, manufacturer, specs, description")

    normalized: dict[str, Any] = {}
    for key, value in data.items():
        target = FIELD_ALIASES.get(key, key)
        if target in normalized and normalized[target] not in (None, ""):
            continue  # основное поле важнее синонима
        normalized[target] = value

    fields = {f: _scalar_to_text(normalized.get(f), f) for f in TEXT_FIELDS}
    fields["specs"] = _parse_specs(normalized.get("specs"))
    return ProductInput(**fields)


def load_product(raw: str | bytes) -> ProductInput:
    """Разбирает JSON-строку. Бросает InputError с указанием места ошибки."""
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise InputError("Файл не в кодировке UTF-8") from exc
    if not raw or not raw.strip():
        raise InputError("Пустой ввод: передайте JSON с данными о товаре")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InputError(f"Некорректный JSON: строка {exc.lineno}, столбец {exc.colno}: {exc.msg}") from exc
    return parse_product(data)
