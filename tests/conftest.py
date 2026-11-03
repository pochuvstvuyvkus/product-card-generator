"""Общие заготовки для тестов. Ни один тест не обращается к реальному API."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from card_gen.input_loader import load_product
from card_gen.models import ProductInput

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"


class FakeClient:
    """Заглушка LLMClient: отдаёт заранее заданные ответы и запоминает промпты."""

    model = "fake-model"

    def __init__(self, *responses):
        self.responses = list(responses)
        self.prompts: list[str] = []

    def complete(self, system: str, user: str, schema: dict) -> str:
        self.prompts.append(user)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response if isinstance(response, str) else json.dumps(response, ensure_ascii=False)


@pytest.fixture
def manometer() -> ProductInput:
    return load_product((EXAMPLES / "manometer_tm510r_m2.json").read_bytes())


@pytest.fixture
def gas_detector() -> ProductInput:
    return load_product((EXAMPLES / "gas_detector_dz1_co.json").read_bytes())


def padded_description(start: str, filler: str, target: int = 1000) -> str:
    text = start
    while len(text) + len(filler) <= target:
        text += filler
    return text


def manometer_draft(**overrides) -> dict:
    """Корректный черновик для манометра: все числа есть во входных данных."""
    draft = {
        "seo_title": "Манометр ТМ-510Р М2 РОСМА, класс точности 1.5, корпус 100 мм",
        "seo_description": padded_description(
            "Манометр ТМ-510Р М2 производства РОСМА измеряет избыточное давление неагрессивных "
            "к медным сплавам жидких и газообразных сред. Класс точности 1.5, диаметр корпуса 100 мм. ",
            "Корпус выполнен из стали, механизм из латунного сплава, присоединение радиальное. ",
        ),
        "key_spec_keys": ["Класс точности", "Диаметр корпуса", "Резьба присоединения"],
        "extracted_specs": [
            {"name": "Диапазон измерений", "value": "0-10 кгс/см2", "source": "name", "quote": "(0-10 кгс/см2)"}
        ],
        "search_queries": ["манометр тм-510р м2", "манометр росма 100 мм", "манометр для жкх"],
        "commercial": {
            "who_fits": ["Организации, обслуживающие объекты ЖКХ"],
            "tasks": ["Контроль избыточного давления воды в системах отопления"],
            "arguments": ["Межповерочный интервал 2 года"],
        },
        "data_issues": [{"field": "specs.Резьба присоединения", "problem": "Указаны два варианта резьбы"}],
    }
    draft.update(overrides)
    return draft
