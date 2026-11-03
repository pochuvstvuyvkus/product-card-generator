"""Собирает входной JSON для card_gen из YML-фида магазина и страницы товара.

В фиде у товаров есть только название, производитель, вид прибора и ссылка,
характеристик и описаний там нет. Поэтому характеристики и описание берутся
со страницы товара по ссылке из фида (блоки #specifications и #description).

Пример:
    python scripts/build_input.py --feed feed.xml --offer-id 190403 --out examples/manometer_tm510r_m2.json
    python scripts/build_input.py --feed feed.xml --offer-id 74022 --out examples/gas_detector_dz1_co.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from bs4 import BeautifulSoup, Tag

USER_AGENT = "Mozilla/5.0 (card_gen prototype)"
SUPERSCRIPT = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def find_offer(feed: Path, offer_id: str) -> dict[str, str]:
    """Потоково читает фид до нужного offer. Фид может быть недокачан до конца."""
    try:
        for _, elem in ET.iterparse(feed, events=("end",)):
            if elem.tag != "offer":
                continue
            if elem.get("id") == offer_id:
                return {child.tag: (child.text or "").strip() for child in elem if child.tag != "param"}
            elem.clear()
    except ET.ParseError as exc:
        sys.exit(f"Фид оборвался раньше, чем нашёлся offer {offer_id}: {exc}")
    sys.exit(f"offer {offer_id} не найден в {feed}")


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=40) as response:
        return response.read().decode("utf-8", errors="replace")


def _text(node: Tag) -> str:
    for sup in node.find_all("sup"):
        sup.replace_with(sup.get_text(strip=True).translate(SUPERSCRIPT))
    text = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
    return re.sub(r"\s+([⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+)", r"\1", text)  # «мг/м ³» превращается в «мг/м³»


def parse_specs(soup: BeautifulSoup) -> dict[str, str]:
    block = soup.find(id="specifications")
    table = block.find("table") if block else None
    if table is None:
        return {}
    specs: dict[str, str] = {}
    section = ""
    last_key = None
    for row in table.find_all("tr"):
        if row.find_parent("thead"):
            continue
        cells = row.find_all("td")
        if len(cells) == 1 and cells[0].get("colspan") == "2":
            section = _text(cells[0]).rstrip(":")  # подзаголовок группы строк
            continue
        if len(cells) == 1 and last_key:
            specs[last_key] += "; " + _text(cells[0])  # продолжение строки с rowspan
            continue
        if len(cells) < 2:
            continue
        raw_key = _text(cells[0])
        key = raw_key.rstrip(":").strip()
        value = _text(cells[1])
        # Строки группы оформлены как «Окружающая среда:», первая строка без
        # двоеточия после подзаголовка значит, что группа закончилась
        if section and raw_key.endswith(":"):
            key = f"{section} ({key[0].lower() + key[1:]})"
        else:
            section = ""
        specs[key] = value
        last_key = key
    return specs


def parse_description(soup: BeautifulSoup) -> str:
    block = soup.find(id="description")
    inner = block.select_one(".long-short-block__inner") if block else None
    if inner is None:
        return ""
    for table in inner.find_all("table"):
        rows = [" | ".join(_text(td) for td in tr.find_all(["td", "th"])) for tr in table.find_all("tr")]
        table.replace_with("\n" + "\n".join(r for r in rows if r.strip(" |")) + "\n")
    for br in inner.find_all("br"):
        br.replace_with("\n")
    for tag in inner.find_all(["p", "li", "h2", "h3", "h4", "div"]):
        tag.insert_after("\n")
    lines = [re.sub(r"[ \t\xa0]+", " ", line).strip() for line in inner.get_text().splitlines()]
    return re.sub(r"\n{2,}", "\n", "\n".join(line for line in lines if line)).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--feed", type=Path, required=True)
    parser.add_argument("--offer-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--page-html", type=Path, help="сохранённая страница товара вместо загрузки по url")
    args = parser.parse_args()

    offer = find_offer(args.feed, args.offer_id)
    html = args.page_html.read_text(encoding="utf-8") if args.page_html else fetch(offer["url"])
    soup = BeautifulSoup(html, "html.parser")

    category = offer.get("typePrefix", "")
    name = f"{category[:1].upper()}{category[1:]} {offer['name']}".strip()
    product = {
        "name": name,
        "manufacturer": offer.get("vendor", ""),
        "category": category,
        "sku": offer.get("vendorCode", ""),
        "url": offer.get("url", ""),
        "specs": parse_specs(soup),
        "description": parse_description(soup),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(product, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{args.out}: {len(product['specs'])} характеристик, описание {len(product['description'])} символов")


if __name__ == "__main__":
    main()
