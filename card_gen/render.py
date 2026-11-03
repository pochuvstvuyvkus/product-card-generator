"""Карточка в Markdown для контент-менеджера."""

from __future__ import annotations

from .checks import DESCRIPTION_MAX, DESCRIPTION_MIN, TITLE_MAX
from .models import Card, Issue

STATUS_TEXT = {
    "ready": "готово к вычитке: автоматические проверки пройдены, вопросов к данным нет",
    "needs_data": "нужны данные: текст прошёл проверки, но во входных данных есть пробелы (см. «Что уточнить»)",
    "needs_review": "нужна правка: черновик не прошёл автоматические проверки (см. «Проверка»)",
}
SOURCE_NOTE = {"specs": "", "name": " *(из названия)*", "description": " *(из описания)*", "missing": ""}


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _list(items: list[str]) -> list[str]:
    return [f"- {i}" for i in items] or ["- данных нет"]


def render_issues(issues: list[Issue]) -> list[str]:
    return [
        f"- **{_cell(i.field)}**: {i.message}" + (" *(замечание модели)*" if i.source == "модель" else "")
        for i in issues
    ]


def render_markdown(card: Card) -> str:
    title_len, desc_len = len(card.seo_title), len(card.seo_description)
    lines = [
        f"# {card.name}",
        "",
        f"**Производитель:** {card.manufacturer}  ",
        f"**Статус:** {STATUS_TEXT[card.status]}",
        "",
        f"## SEO-заголовок ({title_len} из {TITLE_MAX} символов)",
        "",
        card.seo_title,
        "",
        f"## SEO-описание ({desc_len} символов, норма {DESCRIPTION_MIN}–{DESCRIPTION_MAX})",
        "",
        card.seo_description,
        "",
        "## Ключевые характеристики",
        "",
        "| Характеристика | Значение |",
        "|---|---|",
    ]
    for spec in card.key_specs:
        value = f"**{spec.value}**" if spec.source == "missing" else _cell(spec.value)
        lines.append(f"| {_cell(spec.name)} | {value}{SOURCE_NOTE[spec.source]} |")

    lines += ["", "## Поисковые запросы", "", *_list(card.search_queries)]
    lines += [
        "",
        "## Для менеджера",
        "",
        "**Кому подходит**",
        "",
        *_list(card.commercial.who_fits),
        "",
        "**Какие задачи решает**",
        "",
        *_list(card.commercial.tasks),
        "",
        "**Аргументы для клиента**",
        "",
        *_list(card.commercial.arguments),
    ]
    if card.data_issues:
        lines += ["", "## Что уточнить", "", *render_issues(card.data_issues)]
    if card.warnings:
        lines += ["", "## Проверка", "", *[f"- {w}" for w in card.warnings]]
    lines += ["", "---", f"*Черновик подготовлен моделью {card.model}, попыток генерации: {card.attempts}.*", ""]
    return "\n".join(lines)
