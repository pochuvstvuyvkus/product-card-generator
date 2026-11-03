import pytest

from card_gen.checks import InsufficientDataError
from card_gen.generator import generate_card
from card_gen.llm import LLMError
from card_gen.models import NO_DATA, ProductInput

from .conftest import FakeClient, manometer_draft


def test_happy_path_builds_specs_from_input(manometer):
    client = FakeClient(manometer_draft())
    card = generate_card(manometer, client)

    assert client.prompts and len(client.prompts) == 1
    assert card.attempts == 1
    assert card.warnings == []
    specs = {s.name: (s.value, s.source) for s in card.key_specs}
    # значения берутся из входа без изменений, а не из ответа модели
    assert specs["Резьба присоединения"] == ("G½ или M20×1,5", "specs")
    assert specs["Диапазон измерений"] == ("0-10 кгс/см2", "name")
    assert card.status == "needs_data"
    messages = [i.message for i in card.data_issues]
    assert any("взято из названия" in m for m in messages)
    assert not any("обычно указывают" in m for m in messages)  # замечание уже закрыто значением из названия
    assert any(i.source == "модель" for i in card.data_issues)


def test_missing_typical_spec_is_marked_no_data(manometer):
    card = generate_card(manometer, FakeClient(manometer_draft(extracted_specs=[])))
    assert ("Диапазон измерений", NO_DATA, "missing") in [(s.name, s.value, s.source) for s in card.key_specs]
    assert any("обычно указывают" in i.message for i in card.data_issues)


def test_invented_number_triggers_retry_with_feedback(manometer):
    bad = manometer_draft(seo_title="Манометр ТМ-510Р М2 РОСМА, IP65")
    client = FakeClient(bad, manometer_draft())
    card = generate_card(manometer, client)

    assert card.attempts == 2
    assert card.warnings == []
    assert "65" in client.prompts[1] and "<previous_draft>" in client.prompts[1]


def test_violation_left_after_retry_is_reported(manometer):
    bad = manometer_draft(seo_description="Слишком коротко.")
    card = generate_card(manometer, FakeClient(bad, bad))
    assert card.status == "needs_review"
    assert any("SEO-описание" in w for w in card.warnings)


def test_best_attempt_is_kept(manometer):
    worse = manometer_draft(seo_title="М" * 80, seo_description="коротко")
    better = manometer_draft(seo_title="М" * 80)
    card = generate_card(manometer, FakeClient(better, worse))
    assert card.seo_description == better["seo_description"]


def test_no_retry_when_disabled(manometer):
    client = FakeClient(manometer_draft(seo_title="М" * 80))
    card = generate_card(manometer, client, fix_attempts=0)
    assert len(client.prompts) == 1
    assert card.status == "needs_review"


def test_invalid_model_json_is_retried(manometer):
    card = generate_card(manometer, FakeClient("{не json", manometer_draft()))
    assert card.attempts == 2
    assert card.warnings == []


def test_invalid_model_json_twice_raises(manometer):
    with pytest.raises(LLMError, match="не по схеме"):
        generate_card(manometer, FakeClient("{не json", {"seo_title": "только заголовок"}))


def test_api_error_propagates(manometer):
    with pytest.raises(LLMError, match="лимит"):
        generate_card(manometer, FakeClient(LLMError("Превышен лимит запросов к API (429)")))


def test_insufficient_data_does_not_call_model():
    client = FakeClient()
    with pytest.raises(InsufficientDataError):
        generate_card(ProductInput(name="", specs={"a": "b"}), client)
    assert client.prompts == []


def test_prompt_contains_only_input_data_and_gap_hint(manometer):
    client = FakeClient(manometer_draft())
    generate_card(manometer, client)
    prompt = client.prompts[0]
    assert "<product>" in prompt and "ТМ-510Р.00(0-10 кгс/см2)G1/2.М2" in prompt
    assert "«Диапазон измерений»" in prompt  # подсказка о пробеле во входе
    assert manometer.url not in prompt  # служебные поля модели не нужны
