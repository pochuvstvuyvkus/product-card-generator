"""Модели данных: вход, ответ модели и итоговая карточка."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

NO_DATA = "данных нет"


class ProductInput(BaseModel):
    """Нормализованные данные о товаре (после input_loader)."""

    name: str = ""
    manufacturer: str = ""
    specs: dict[str, str] = Field(default_factory=dict)
    description: str = ""
    # Необязательные поля, которые есть в фиде магазина
    category: str = ""
    url: str = ""
    sku: str = ""


class Issue(BaseModel):
    """Замечание к входным данным: чего нет или что нужно уточнить."""

    field: str
    message: str
    source: Literal["проверка", "модель"] = "проверка"


# --- ответ модели -------------------------------------------------------------


class ExtractedSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: str
    source: Literal["name", "description"]
    quote: str


class Commercial(BaseModel):
    model_config = ConfigDict(extra="forbid")

    who_fits: list[str]
    tasks: list[str]
    arguments: list[str]


class ModelIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    problem: str


class LLMDraft(BaseModel):
    """То, что возвращает модель. Схема для API лежит в prompts.DRAFT_SCHEMA."""

    model_config = ConfigDict(extra="forbid")

    seo_title: str
    seo_description: str
    key_spec_keys: list[str]
    extracted_specs: list[ExtractedSpec]
    search_queries: list[str]
    commercial: Commercial
    data_issues: list[ModelIssue]


# --- итоговая карточка --------------------------------------------------------


class SpecItem(BaseModel):
    name: str
    value: str
    # specs: из входных характеристик; name/description: найдено в названии
    # или описании и подтверждено цитатой; missing: значения нет во входе
    source: Literal["specs", "name", "description", "missing"]


class Card(BaseModel):
    # ready: проверки пройдены, вопросов к данным нет
    # needs_data: текст прошёл проверки, но во входных данных есть пробелы
    # needs_review: черновик не прошёл автоматические проверки (см. warnings)
    status: Literal["ready", "needs_data", "needs_review"]
    name: str
    manufacturer: str
    seo_title: str
    seo_description: str
    key_specs: list[SpecItem]
    search_queries: list[str]
    commercial: Commercial
    data_issues: list[Issue]
    warnings: list[str]
    model: str
    attempts: int
