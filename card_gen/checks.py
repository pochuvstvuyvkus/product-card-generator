"""Детерминированные проверки: полнота входа и черновик модели.

Здесь нет обращений к LLM. Всё, что можно проверить кодом, проверяется кодом:
пропуски во входных данных, длины текстов, числа, которых нет во входе,
и цитаты, на которые модель ссылается при извлечении характеристик.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .models import Issue, LLMDraft, ProductInput

TITLE_MAX = 70
DESCRIPTION_MIN = 800
DESCRIPTION_MAX = 1200
QUERIES_MIN = 3
QUERIES_MAX = 5
SHORT_DESCRIPTION = 150


class InsufficientDataError(ValueError):
    """Данных так мало, что генерировать карточку бессмысленно."""

    def __init__(self, issues: list[Issue]):
        self.issues = issues
        super().__init__("; ".join(i.message for i in issues))


# --- типовые характеристики по видам приборов ---------------------------------


@dataclass(frozen=True)
class Param:
    title: str
    synonyms: tuple[str, ...]  # подстроки в названии характеристики, нижний регистр


@dataclass(frozen=True)
class Profile:
    title: str
    triggers: tuple[str, ...]  # подстроки в названии или категории товара
    params: tuple[Param, ...]


RANGE = Param(
    "Диапазон измерений",
    ("диапазон измерен", "диапазон показаний", "диапазон обнаружен", "диапазон контрол", "предел"),
)
ACCURACY = Param("Класс точности / погрешность", ("класс точности", "точност", "погрешност"))
POWER = Param("Питание", ("питани",))
PROTECTION = Param("Степень защиты", ("степень защиты", "ip"))

PROFILES: tuple[Profile, ...] = (
    Profile(
        "манометр",
        ("манометр", "вакуумметр", "мановакуумметр", "напоромер", "тягомер"),
        (
            RANGE,
            Param("Класс точности", ("класс точности", "точност")),
            Param("Резьба присоединения", ("резьба", "присоединени")),
            Param("Диаметр корпуса", ("диаметр",)),
        ),
    ),
    Profile(
        "газоанализатор или сигнализатор газа",
        (
            "газоанализатор",
            "загазованност",
            "детектор утечк",
            "течеискатель",
            "горючих газ",
            "токсичных газ",
            "угарного газа",
        ),
        (
            Param("Контролируемый газ", ("газ",)),
            RANGE,
            Param("Тип сенсора", ("тип чэ", "сенсор", "чувствительн", "датчик")),
            POWER,
            PROTECTION,
        ),
    ),
    Profile(
        "датчик давления",
        ("датчик давления", "преобразователь давления"),
        (RANGE, ACCURACY, Param("Выходной сигнал", ("выход",)), POWER),
    ),
    Profile(
        "термометр или термопреобразователь",
        ("термометр", "термопреобразовател", "термопар"),
        (
            Param("Диапазон температур", ("диапазон измерен", "диапазон температур", "температура измеряемой")),
            ACCURACY,
            Param("Длина погружаемой части", ("длина",)),
        ),
    ),
)


def detect_profile(product: ProductInput) -> Profile | None:
    haystack = f"{product.category} {product.name}".lower()
    for profile in PROFILES:
        if any(t in haystack for t in profile.triggers):
            return profile
    return None


def find_spec_key(param: Param, keys: list[str]) -> str | None:
    for key in keys:
        low = key.lower()
        for syn in param.synonyms:
            # «ip» ищем как отдельное слово, иначе совпадёт с «тип»
            if syn == "ip":
                if re.search(r"\bip\b", low):
                    return key
            elif syn in low:
                return key
    return None


def missing_profile_params(product: ProductInput) -> list[Param]:
    profile = detect_profile(product)
    if profile is None:
        return []
    keys = [k for k, v in product.specs.items() if v]
    return [p for p in profile.params if find_spec_key(p, keys) is None]


# --- полнота входных данных ---------------------------------------------------


def check_input(product: ProductInput) -> list[Issue]:
    """Возвращает замечания к входу. Бросает InsufficientDataError, если писать не из чего."""
    issues: list[Issue] = []
    fatal: list[Issue] = []

    if not product.name:
        fatal.append(Issue(field="name", message="Нет названия товара: без него карточку не собрать"))
    if not product.specs and not product.description:
        fatal.append(
            Issue(
                field="specs, description",
                message="Нет ни характеристик, ни описания: тексту не на чем основываться",
            )
        )
    if fatal:
        raise InsufficientDataError(fatal)

    if not product.manufacturer:
        issues.append(Issue(field="manufacturer", message="Не указан производитель"))
    if not product.specs:
        issues.append(Issue(field="specs", message="Характеристики не переданы: список характеристик будет пустым"))
    for key, value in product.specs.items():
        if not value:
            issues.append(Issue(field=f"specs.{key}", message=f"У характеристики «{key}» пустое значение"))
    if not product.description:
        issues.append(Issue(field="description", message="Нет описания: текст построен только на характеристиках"))
    elif len(product.description) < SHORT_DESCRIPTION:
        issues.append(
            Issue(
                field="description",
                message=f"Описание очень короткое ({len(product.description)} символов): текст выйдет общим",
            )
        )

    profile = detect_profile(product)
    for param in missing_profile_params(product):
        issues.append(
            Issue(
                field=f"specs.{param.title}",
                message=f"Для прибора типа «{profile.title}» обычно указывают «{param.title}», в характеристиках этого нет",
            )
        )
    return issues


# --- числа --------------------------------------------------------------------

_FRACTIONS = {"½": "1/2", "¼": "1/4", "¾": "3/4", "⅓": "1/3", "⅔": "2/3"}
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")


def _canonical(number: str) -> str:
    try:
        return format(Decimal(number.replace(",", ".")).normalize(), "f")
    except InvalidOperation:
        return number


def numbers_in(text: str) -> set[str]:
    """Все числа в тексте в каноническом виде: «1,50» и «1.5» дают «1.5»."""
    for char, repl in _FRACTIONS.items():
        text = text.replace(char, repl)
    return {_canonical(n) for n in _NUMBER_RE.findall(text)}


def input_numbers(product: ProductInput) -> set[str]:
    parts = [product.name, product.manufacturer, product.description, product.category, product.sku]
    for key, value in product.specs.items():
        parts.extend((key, value))
    return numbers_in("\n".join(parts))


def unknown_numbers(text: str, allowed: set[str]) -> list[str]:
    return sorted(numbers_in(text) - allowed, key=lambda n: (len(n), n))


# --- проверка черновика -------------------------------------------------------


def _norm_ws(text: str) -> str:
    for char, repl in _FRACTIONS.items():
        text = text.replace(char, repl)
    return re.sub(r"\s+", " ", text).strip().lower()


@dataclass
class DraftReport:
    """Результат проверки черновика.

    fixable: нарушения, которые стоит отдать модели на исправление (длины, числа).
    dropped: что код выбросил из черновика сам (неизвестные ключи, цитаты без подтверждения).
    """

    fixable: list[str]
    dropped: list[str]
    valid_spec_keys: list[str]
    valid_extracted: list


def check_draft(draft: LLMDraft, product: ProductInput) -> DraftReport:
    fixable: list[str] = []
    dropped: list[str] = []

    title_len = len(draft.seo_title)
    if title_len > TITLE_MAX:
        fixable.append(f"SEO-заголовок {title_len} символов, нужно не больше {TITLE_MAX}")
    if not draft.seo_title.strip():
        fixable.append("SEO-заголовок пустой")

    desc_len = len(draft.seo_description)
    if desc_len < DESCRIPTION_MIN:
        fixable.append(
            f"SEO-описание {desc_len} символов, нужно {DESCRIPTION_MIN}–{DESCRIPTION_MAX}: добавьте около {DESCRIPTION_MIN + 100 - desc_len} символов по фактам из входных данных"
        )
    elif desc_len > DESCRIPTION_MAX:
        fixable.append(
            f"SEO-описание {desc_len} символов, нужно {DESCRIPTION_MIN}–{DESCRIPTION_MAX}: сократите примерно на {desc_len - DESCRIPTION_MAX + 100} символов"
        )

    queries = [q for q in draft.search_queries if q.strip()]
    if not QUERIES_MIN <= len(queries) <= QUERIES_MAX:
        fixable.append(f"Поисковых запросов {len(queries)}, нужно от {QUERIES_MIN} до {QUERIES_MAX}")

    allowed = input_numbers(product)
    texts = {
        "SEO-заголовок": draft.seo_title,
        "SEO-описание": draft.seo_description,
        "поисковые запросы": "\n".join(draft.search_queries),
        "коммерческий блок": "\n".join(draft.commercial.who_fits + draft.commercial.tasks + draft.commercial.arguments),
    }
    for label, text in texts.items():
        extra = unknown_numbers(text, allowed)
        if extra:
            fixable.append(
                f"В блоке «{label}» есть числа, которых нет во входных данных: {', '.join(extra)}. Уберите их или замените значениями из входа"
            )

    valid_keys: list[str] = []
    for key in draft.key_spec_keys:
        if key in product.specs and key not in valid_keys:
            valid_keys.append(key)
        elif key not in product.specs:
            dropped.append(f"Модель указала характеристику «{key}», которой нет во входе: не включена")

    sources = {"name": _norm_ws(product.name), "description": _norm_ws(product.description)}
    valid_extracted = []
    for spec in draft.extracted_specs:
        quote = _norm_ws(spec.quote)
        if not quote or quote not in sources[spec.source]:
            dropped.append(f"Характеристика «{spec.name}: {spec.value}» не подтверждена цитатой из входа: не включена")
            continue
        if not numbers_in(spec.value) <= numbers_in(spec.quote):
            dropped.append(f"В значении «{spec.name}: {spec.value}» есть числа, которых нет в цитате: не включена")
            continue
        valid_extracted.append(spec)

    return DraftReport(fixable, dropped, valid_keys, valid_extracted)
