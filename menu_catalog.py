"""Load menu JSON, assign stable item ids, and resolve items for cart/detail views."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_PRICE_NUM_RE = re.compile(r"[\d.]+")


def slugify(text: str) -> str:
    s = _SLUG_RE.sub("-", text.lower()).strip("-")
    return s or "item"


def enrich_menu(data: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(data)
    for cat in out.get("categories", []):
        cid = cat.get("id") or slugify(str(cat.get("title", "category")))
        cat["id"] = cid
        counts: dict[str, int] = {}
        for item in cat.get("items", []):
            base = slugify(str(item.get("name", "")))
            n = counts.get(base, 0) + 1
            counts[base] = n
            suffix = "" if n == 1 else f"-{n}"
            item["id"] = f"{cid}__{base}{suffix}"
    return out


def load_enriched_menu(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        raw = json.load(f)
    return enrich_menu(raw)


def find_item(menu: dict[str, Any], item_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    for cat in menu.get("categories", []):
        for item in cat.get("items", []):
            if item.get("id") == item_id:
                return cat, item
    return None


def price_to_cents(price: str | None) -> int:
    if not price:
        return 0
    m = _PRICE_NUM_RE.search(price.replace(",", ""))
    if not m:
        return 0
    return int(round(float(m.group()) * 100))


def format_aud(cents: int) -> str:
    if cents % 100 == 0:
        return f"${cents // 100}"
    return f"${cents / 100:.2f}"
