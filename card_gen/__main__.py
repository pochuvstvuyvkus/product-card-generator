"""CLI: python -m card_gen examples/manometer_tm510r_m2.json --format md"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .checks import InsufficientDataError, check_input
from .config import ConfigError, Settings
from .generator import generate_card
from .input_loader import InputError, load_product
from .llm import AnthropicClient, LLMError
from .render import render_issues, render_markdown

EXIT_INPUT, EXIT_CONFIG, EXIT_LLM = 2, 3, 4


def _read(source: str) -> bytes:
    if source == "-":
        return sys.stdin.buffer.read()
    path = Path(source)
    if not path.is_file():
        raise InputError(f"Файл не найден: {source}")
    return path.read_bytes()


def _check_only(raw: bytes, fmt: str) -> str:
    product = load_product(raw)
    try:
        issues = check_input(product)
    except InsufficientDataError as exc:
        issues = exc.issues
    if fmt == "json":
        return json.dumps([i.model_dump() for i in issues], ensure_ascii=False, indent=2)
    return "\n".join(render_issues(issues)) or "Замечаний к входным данным нет"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="card_gen", description="Черновик карточки товара по JSON с данными прибора")
    parser.add_argument("inputs", nargs="+", help="JSON-файлы с товарами или - для чтения из stdin")
    parser.add_argument("--format", choices=["md", "json"], default="md", help="формат вывода в stdout")
    parser.add_argument("--out-dir", type=Path, help="сохранить <имя>.md и <имя>.json в эту папку")
    parser.add_argument("--check-only", action="store_true", help="только проверить входные данные, без LLM")
    parser.add_argument("-v", "--verbose", action="store_true", help="подробный лог в stderr")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")

    client = None
    exit_code = 0
    for source in args.inputs:
        try:
            raw = _read(source)
            if args.check_only:
                print(_check_only(raw, args.format))
                continue
            product = load_product(raw)
            if client is None:
                settings = Settings.from_env()
                client = AnthropicClient(settings)
            card = generate_card(product, client, fix_attempts=client.fix_attempts)
        except InputError as exc:
            print(f"[{source}] Ошибка входных данных: {exc}", file=sys.stderr)
            exit_code = EXIT_INPUT
            continue
        except InsufficientDataError as exc:
            print(f"[{source}] Недостаточно данных для карточки:", file=sys.stderr)
            print("\n".join(render_issues(exc.issues)), file=sys.stderr)
            exit_code = EXIT_INPUT
            continue
        except ConfigError as exc:
            print(f"Ошибка настройки: {exc}", file=sys.stderr)
            return EXIT_CONFIG
        except LLMError as exc:
            print(f"[{source}] Ошибка LLM: {exc}", file=sys.stderr)
            exit_code = EXIT_LLM
            continue

        markdown = render_markdown(card)
        card_json = json.dumps(card.model_dump(), ensure_ascii=False, indent=2)
        if args.out_dir:
            args.out_dir.mkdir(parents=True, exist_ok=True)
            stem = Path(source).stem if source != "-" else "card"
            (args.out_dir / f"{stem}.md").write_text(markdown, encoding="utf-8")
            (args.out_dir / f"{stem}.json").write_text(card_json + "\n", encoding="utf-8")
            print(f"[{source}] сохранено: {args.out_dir / stem}.md, .json (статус: {card.status})", file=sys.stderr)
        else:
            print(markdown if args.format == "md" else card_json)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
