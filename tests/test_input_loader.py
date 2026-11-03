import json

import pytest

from card_gen.input_loader import InputError, load_product


def test_valid_input_is_normalized():
    raw = json.dumps(
        {
            "name": "  Манометр DM 02 ",
            "vendor": "Манотомь",
            "specs": {"класс точности": 1.5, "с подсветкой": False, "резьба": ["G1/2", "M20x1,5"]},
            "description": "<p>Прибор&nbsp;для <b>давления</b></p><p>Второй абзац</p>",
        }
    )
    product = load_product(raw)
    assert product.name == "Манометр DM 02"
    assert product.manufacturer == "Манотомь"  # синоним vendor
    assert product.specs == {"класс точности": "1.5", "с подсветкой": "нет", "резьба": "G1/2, M20x1,5"}
    assert product.description == "Прибор для давления\n\nВторой абзац"


@pytest.mark.parametrize(
    "raw, message",
    [
        ('{"name": "Манометр",}', "Некорректный JSON: строка 1"),
        ("", "Пустой ввод"),
        ("   ", "Пустой ввод"),
        ("[1, 2]", "Ожидается JSON-объект"),
        ('{"name": ["a"]}', "«name» должно быть строкой"),
        ('{"name": "x", "specs": "диапазон 0-1"}', "«specs» должно быть объектом"),
        ('{"name": "x", "specs": {"": "1"}}', "пустым названием"),
        ('{"name": "x", "specs": [42]}', r"specs\[0\]"),
    ],
)
def test_invalid_input_raises_readable_error(raw, message):
    with pytest.raises(InputError, match=message):
        load_product(raw)


def test_specs_as_list_and_bom_bytes():
    raw = '﻿{"name": "x", "specs": [{"name": "Диапазон", "value": "0–1 МПа"}, "Класс точности: 1,5"]}'
    product = load_product(raw.encode("utf-8"))
    assert product.specs == {"Диапазон": "0–1 МПа", "Класс точности": "1,5"}


def test_non_utf8_bytes():
    with pytest.raises(InputError, match="UTF-8"):
        load_product('{"name": "Манометр"}'.encode("cp1251"))


def test_null_and_missing_fields_become_empty():
    product = load_product('{"name": "Манометр", "manufacturer": null, "specs": {"Диапазон": null}}')
    assert product.manufacturer == ""
    assert product.specs == {"Диапазон": ""}
    assert product.description == ""
