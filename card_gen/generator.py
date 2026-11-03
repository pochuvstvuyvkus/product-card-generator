"""Сборка карточки: вход, проверки, модель, проверка черновика, итоговая карточка."""

from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from .checks import DraftReport, check_draft, check_input, find_spec_key, missing_profile_params
from .llm import LLMClient, LLMError
from .models import NO_DATA, Card, Issue, LLMDraft, ProductInput, SpecItem
from .prompts import DRAFT_SCHEMA, SYSTEM_PROMPT, build_fix_prompt, build_user_prompt

log = logging.getLogger(__name__)


def _parse_draft(text: str) -> LLMDraft:
    return LLMDraft.model_validate(json.loads(text))


def _build_specs(product: ProductInput, report: DraftReport) -> list[SpecItem]:
    """Список характеристик собирается кодом: значения берутся из входа без изменений.

    Модель только выбирает, какие характеристики главные, и находит значения
    в названии или описании (с цитатой, которую код уже сверил с источником).
    """
    keys = report.valid_spec_keys or [k for k, v in product.specs.items() if v]
    items = [SpecItem(name=k, value=product.specs[k], source="specs") for k in keys if product.specs[k]]

    extracted = list(report.valid_extracted)
    for param in missing_profile_params(product):
        match = next(
            (s for s in extracted if find_spec_key(param, [s.name]) is not None),
            None,
        )
        if match:
            extracted.remove(match)
            items.append(SpecItem(name=match.name, value=match.value, source=match.source))
        else:
            items.append(SpecItem(name=param.title, value=NO_DATA, source="missing"))

    known = {i.name.lower() for i in items}
    for spec in extracted:
        if spec.name.lower() not in known:
            items.append(SpecItem(name=spec.name, value=spec.value, source=spec.source))
    return items


def _extracted_issues(items: list[SpecItem]) -> list[Issue]:
    where = {"name": "названия", "description": "описания"}
    return [
        Issue(
            field=f"specs.{i.name}",
            message=f"Значение «{i.value}» взято из {where[i.source]}: проверьте и внесите в характеристики",
        )
        for i in items
        if i.source in where
    ]


def generate_card(product: ProductInput, client: LLMClient, fix_attempts: int = 1) -> Card:
    """Главная функция. Бросает InsufficientDataError (из check_input) и LLMError."""
    input_issues = check_input(product)
    user_prompt = build_user_prompt(product)

    best: tuple[LLMDraft, DraftReport] | None = None
    attempts = 0
    prompt = user_prompt
    for attempt in range(1 + fix_attempts):
        attempts = attempt + 1
        text = client.complete(SYSTEM_PROMPT, prompt, DRAFT_SCHEMA)
        try:
            draft = _parse_draft(text)
        except (json.JSONDecodeError, ValidationError) as exc:
            log.warning("попытка %s: ответ не по схеме: %s", attempts, exc)
            if attempt == fix_attempts:
                if best is None:
                    raise LLMError("Модель вернула ответ не по схеме даже после повторной попытки") from exc
                break
            prompt = build_fix_prompt(product, text[:4000], ["Ответ не соответствует JSON-схеме: верни валидный JSON"])
            continue

        report = check_draft(draft, product)
        if best is None or len(report.fixable) < len(best[1].fixable):
            best = (draft, report)
        if not report.fixable:
            break
        log.info("попытка %s: нарушения: %s", attempts, report.fixable)
        prompt = build_fix_prompt(product, draft.model_dump_json(indent=2), report.fixable)

    assert best is not None
    draft, report = best

    key_specs = _build_specs(product, report)
    # Если пропущенная типовая характеристика нашлась в названии или описании,
    # общее замечание «в характеристиках нет» заменяется на «взято из названия»
    still_missing = {f"specs.{i.name}" for i in key_specs if i.source == "missing"}
    resolved = {f"specs.{p.title}" for p in missing_profile_params(product)} - still_missing
    input_issues = [i for i in input_issues if i.field not in resolved]
    model_issues = [Issue(field=i.field, message=i.problem, source="модель") for i in draft.data_issues]
    issues = input_issues + _extracted_issues(key_specs) + model_issues
    warnings = report.fixable + report.dropped

    status = "needs_review" if warnings else "needs_data" if issues else "ready"
    return Card(
        status=status,
        name=product.name,
        manufacturer=product.manufacturer or NO_DATA,
        seo_title=draft.seo_title,
        seo_description=draft.seo_description,
        key_specs=key_specs,
        search_queries=[q.strip() for q in draft.search_queries if q.strip()],
        commercial=draft.commercial,
        data_issues=issues,
        warnings=warnings,
        model=client.model,
        attempts=attempts,
    )
