import pytest

from card_gen.checks import (
    InsufficientDataError,
    check_draft,
    check_input,
    input_numbers,
    numbers_in,
    unknown_numbers,
)
from card_gen.models import LLMDraft, ProductInput

from .conftest import manometer_draft


def test_no_name_is_fatal():
    with pytest.raises(InsufficientDataError, match="Нет названия"):
        check_input(ProductInput(specs={"Диапазон": "0–1 МПа"}))


def test_no_specs_and_no_description_is_fatal():
    with pytest.raises(InsufficientDataError) as exc:
        check_input(ProductInput(name="Манометр", manufacturer="X"))
    assert exc.value.issues[0].field == "specs, description"


def test_partial_input_reports_every_gap():
    product = ProductInput(
        name="Манометр МП-100", specs={"Класс точности": "1,5", "Резьба": ""}, description="Коротко."
    )
    fields = {i.field for i in check_input(product)}
    assert "manufacturer" in fields
    assert "specs.Резьба" in fields  # пустое значение
    assert "description" in fields  # слишком короткое
    assert "specs.Диапазон измерений" in fields  # типовая характеристика манометра
    assert "specs.Диаметр корпуса" in fields


def test_real_manometer_lacks_range_in_specs(manometer):
    issues = check_input(manometer)
    assert [i.field for i in issues] == ["specs.Диапазон измерений"]


def test_real_gas_detector_is_complete(gas_detector):
    assert check_input(gas_detector) == []


def test_temperature_range_is_not_a_measuring_range():
    product = ProductInput(name="Манометр", description="текст", specs={"Диапазон рабочих температур": "−60…+60"})
    assert "specs.Диапазон измерений" in {i.field for i in check_input(product)}


def test_numbers_are_canonical():
    assert numbers_in("класс 1,5 и 1.50, резьба G½, 0–10 кгс/см²") == {"1.5", "1", "2", "0", "10"}


def test_unknown_numbers_catch_invented_values(manometer):
    allowed = input_numbers(manometer)
    text = "Диапазон 0–1,6 МПа, класс точности 1.5, степень защиты IP65"
    assert unknown_numbers(text, allowed) == ["65", "1.6"]


def test_valid_draft_has_no_violations(manometer):
    report = check_draft(LLMDraft.model_validate(manometer_draft()), manometer)
    assert report.fixable == []
    assert report.dropped == []
    assert report.valid_spec_keys == ["Класс точности", "Диаметр корпуса", "Резьба присоединения"]
    assert len(report.valid_extracted) == 1


@pytest.mark.parametrize(
    "override, expected",
    [
        ({"seo_title": "М" * 71}, "SEO-заголовок 71 символов"),
        ({"seo_description": "Короткий текст."}, "SEO-описание 15 символов"),
        ({"seo_description": "а" * 1300}, "сократите"),
        ({"search_queries": ["манометр"]}, "Поисковых запросов 1"),
        (
            {"seo_title": "Манометр ТМ-510Р М2 на 16 бар"},
            "«SEO-заголовок» есть числа, которых нет во входных данных: 16",
        ),
    ],
)
def test_fixable_violations(manometer, override, expected):
    report = check_draft(LLMDraft.model_validate(manometer_draft(**override)), manometer)
    assert any(expected in v for v in report.fixable), report.fixable


def test_ungrounded_items_are_dropped(manometer):
    draft = manometer_draft(
        key_spec_keys=["Класс точности", "Вес прибора"],
        extracted_specs=[
            {"name": "Масса", "value": "0,5 кг", "source": "description", "quote": "вес 0,5 кг"},
            {"name": "Вес", "value": "0,35 кг", "source": "description", "quote": "0.27"},
        ],
    )
    report = check_draft(LLMDraft.model_validate(draft), manometer)
    assert report.valid_spec_keys == ["Класс точности"]
    assert report.valid_extracted == []
    assert len(report.dropped) == 3
