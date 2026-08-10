"""Kirana catalogue lookup from a public scraped CSV (Voice for Bharat Day 5).

Data source: Zepto-style inventory CSV (scraped public listing dataset), stored
locally at backend/data/zepto_catalogue.csv — not a live store API.
"""

from __future__ import annotations

import csv
import logging
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("catalogue")

DEFAULT_CSV_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "zepto_catalogue.csv"
)
DATA_SOURCE_LABEL = (
    "local Zepto-style inventory CSV (scraped public dataset, not a live API)"
)

# Spoken / Hinglish aliases → catalogue English name fragment to search.
_ALIASES: dict[str, str] = {
    "banana": "banana robusta",
    "bananas": "banana robusta",
    "kela": "banana robusta",
    "kele": "banana robusta",
    "mirchi": "chilli green",
    "hari mirchi": "chilli green",
    "hari mirch": "chilli green",
    "green chilli": "chilli green",
    "green chili": "chilli green",
    "green chillies": "chilli green",
    "pyaz": "onion",
    "pyaaz": "onion",
    "tamatar": "tomato",
    "aloo": "potato",
    "doodh": "milk",
    "cheeni": "sugar",
    "chawal": "rice",
}

_QTY_WORDS = {
    "a",
    "an",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "half",
    "aadha",
    "adha",
    "ek",
    "do",
    "teen",
    "kilo",
    "kg",
    "kilogram",
    "grams",
    "gram",
    "g",
    "litre",
    "liter",
    "litres",
    "liters",
    "l",
    "packet",
    "packets",
    "pack",
    "packs",
    "piece",
    "pieces",
    "pcs",
    "dozen",
}

# Prefer fresh produce over sauces/powders for short grocery queries.
_PRODUCE_HINTS = {
    "banana",
    "onion",
    "tomato",
    "potato",
    "chilli",
    "chili",
    "mirchi",
    "apple",
    "mango",
    "carrot",
    "cucumber",
    "spinach",
    "coriander",
    "garlic",
    "ginger",
}
_NON_PRODUCE_MARKERS = (
    "sauce",
    "powder",
    "masala",
    "pickle",
    "flakes",
    "nugget",
    "sausage",
    "leaf",
)


def _paise_to_rupees(value: str | int | float) -> float | None:
    try:
        paise = float(value)
    except (TypeError, ValueError):
        return None
    # Dataset stores money in paise (e.g. 2500 → ₹25.00).
    return round(paise / 100.0, 2)


def _parse_bool(value: str) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _singularize_token(token: str) -> str:
    if len(token) > 3 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("oes"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def prepare_search_query(query: str) -> str:
    """Strip spoken quantities and map Hinglish aliases before search."""
    q = _normalize(query)
    if not q:
        return ""

    # Drop bare numbers / fractions so "3 bananas" does not match "Mach 3".
    q = re.sub(r"\b\d+(\.\d+)?\b", " ", q)
    q = re.sub(r"\b\d+/\d+\b", " ", q)
    tokens = [_singularize_token(t) for t in q.split() if t not in _QTY_WORDS]
    cleaned = _normalize(" ".join(tokens))
    if not cleaned:
        cleaned = _normalize(query)

    if cleaned in _ALIASES:
        return _ALIASES[cleaned]
    # Try last two tokens (e.g. "please hari mirchi" → "hari mirchi")
    parts = cleaned.split()
    if len(parts) >= 2:
        tail = " ".join(parts[-2:])
        if tail in _ALIASES:
            return _ALIASES[tail]
    if parts and parts[-1] in _ALIASES:
        return _ALIASES[parts[-1]]
    return cleaned


@dataclass
class CatalogueItem:
    category: str
    name: str
    mrp_inr: float | None
    selling_price_inr: float | None
    discount_percent: float | None
    available_quantity: int | None
    weight_gms: int | None
    out_of_stock: bool
    pack_quantity: int | None

    def to_spoken_dict(self, query: str, as_of: str) -> dict[str, Any]:
        stock_status = "out_of_stock" if self.out_of_stock else "in_stock"
        if not self.out_of_stock and self.available_quantity is not None:
            if self.available_quantity <= 0:
                stock_status = "out_of_stock"
            elif self.available_quantity <= 3:
                stock_status = "low_stock"

        return {
            "found": True,
            "query": query,
            "name": self.name,
            "category": self.category,
            "stock_status": stock_status,
            "available_quantity": self.available_quantity,
            "mrp_inr": self.mrp_inr,
            "selling_price_inr": self.selling_price_inr,
            "discount_percent": self.discount_percent,
            "weight_gms": self.weight_gms,
            "pack_quantity": self.pack_quantity,
            "as_of": as_of,
            "data_source": DATA_SOURCE_LABEL,
            "price_note": (
                "Indicative catalogue price only. Shopkeeper confirms the final bill."
            ),
        }


class CatalogueStore:
    """Thread-safe in-memory index over the Zepto CSV catalogue."""

    def __init__(self, csv_path: Path | str | None = None) -> None:
        self.csv_path = Path(csv_path) if csv_path is not None else DEFAULT_CSV_PATH
        self._lock = threading.Lock()
        self._items: list[CatalogueItem] | None = None
        self._as_of: str = ""
        self._load_error: str | None = None

    def _load(self) -> None:
        if self._items is not None:
            return

        if not self.csv_path.is_file():
            self._items = []
            self._load_error = f"Catalogue file missing: {self.csv_path}"
            logger.error(self._load_error)
            return

        items: list[CatalogueItem] = []
        try:
            with self.csv_path.open(newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    name = (row.get("name") or "").strip()
                    if not name:
                        continue
                    discount_raw = row.get("discountPercent")
                    try:
                        discount = (
                            float(discount_raw)
                            if discount_raw not in (None, "")
                            else None
                        )
                    except ValueError:
                        discount = None
                    try:
                        available = int(float(row.get("availableQuantity") or 0))
                    except ValueError:
                        available = None
                    try:
                        weight = int(float(row.get("weightInGms") or 0)) or None
                    except ValueError:
                        weight = None
                    try:
                        pack_qty = int(float(row.get("quantity") or 0)) or None
                    except ValueError:
                        pack_qty = None

                    items.append(
                        CatalogueItem(
                            category=(
                                row.get("Category") or row.get("category") or ""
                            ).strip(),
                            name=name,
                            mrp_inr=_paise_to_rupees(row.get("mrp")),
                            selling_price_inr=_paise_to_rupees(
                                row.get("discountedSellingPrice")
                            ),
                            discount_percent=discount,
                            available_quantity=available,
                            weight_gms=weight,
                            out_of_stock=_parse_bool(row.get("outOfStock") or ""),
                            pack_quantity=pack_qty,
                        )
                    )
        except OSError as exc:
            self._items = []
            self._load_error = f"Could not read catalogue: {exc}"
            logger.exception(self._load_error)
            return

        mtime = (
            datetime.fromtimestamp(self.csv_path.stat().st_mtime, tz=timezone.utc)
            .date()
            .isoformat()
        )
        self._as_of = mtime
        self._items = items
        self._load_error = None
        logger.info(
            "Loaded catalogue rows=%s as_of=%s path=%s",
            len(items),
            self._as_of,
            self.csv_path,
        )

    def _score(self, query: str, item: CatalogueItem) -> int:
        q = _normalize(query)
        n = _normalize(item.name)
        if not q or not n:
            return 0

        score = 0
        if q == n:
            score = 100
        elif n.startswith(q):
            score = 90
        elif q in n:
            score = 75
        else:
            q_tokens = {_singularize_token(t) for t in q.split()}
            n_tokens = {_singularize_token(t) for t in n.split()}
            if not q_tokens:
                return 0
            overlap = len(q_tokens & n_tokens) / len(q_tokens)
            if overlap >= 1.0:
                score = 70
            elif overlap >= 0.5:
                score = 55
            else:
                return 0

        category = _normalize(item.category)
        name_l = n
        produce_query = any(hint in q.split() or hint == q for hint in _PRODUCE_HINTS)
        if produce_query or any(h in q for h in _PRODUCE_HINTS):
            if "fruit" in category or "vegetable" in category:
                score += 15
            if any(marker in name_l for marker in _NON_PRODUCE_MARKERS):
                score -= 40

        return score

    def lookup(self, query: str, limit: int = 3) -> dict[str, Any]:
        """Search catalogue by spoken item name. Never invents rows."""
        with self._lock:
            self._load()
            items = self._items or []
            as_of = self._as_of
            load_error = self._load_error

        if load_error:
            return {
                "found": False,
                "error": True,
                "query": query,
                "message": (
                    "Catalogue is unavailable right now. Do not invent stock or "
                    "prices. Tell the caller you'll note the item for the shopkeeper."
                ),
                "data_source": DATA_SOURCE_LABEL,
            }

        raw = (query or "").strip()
        if not raw:
            return {
                "found": False,
                "error": False,
                "query": query,
                "message": "Need an item name to look up.",
                "data_source": DATA_SOURCE_LABEL,
                "as_of": as_of,
            }

        q = prepare_search_query(raw)
        ranked: list[tuple[int, CatalogueItem]] = []
        for item in items:
            score = self._score(q, item)
            if score > 0:
                ranked.append((score, item))
        # Higher score first; prefer shorter product names on ties.
        ranked.sort(
            key=lambda pair: (-pair[0], len(pair[1].name), pair[1].name.lower())
        )

        if not ranked:
            return {
                "found": False,
                "error": False,
                "query": query,
                "search_query": q,
                "message": (
                    f"No catalogue match for '{raw}'. Say you could not find it in "
                    "today's list and offer to note it for the shopkeeper."
                ),
                "data_source": DATA_SOURCE_LABEL,
                "as_of": as_of,
            }

        top = ranked[: max(1, limit)]
        matches = [item.to_spoken_dict(raw, as_of) for _, item in top]
        best = matches[0]
        return {
            **best,
            "search_query": q,
            "matches": matches,
            "match_count": len(matches),
            "speak_hint": (
                f"Say the item name, stock, and about {best.get('selling_price_inr')} "
                "rupees as an indicative catalogue rate. Mention pack/weight if useful. "
                "Shopkeeper confirms the final bill."
            ),
        }

    def estimate_line_total(self, query: str, quantity: float) -> dict[str, Any]:
        """Indicative line total = selling price * quantity (if in stock)."""
        result = self.lookup(query, limit=1)
        if not result.get("found"):
            return result
        price = result.get("selling_price_inr")
        if price is None:
            result["estimated_total_inr"] = None
            result["message"] = "Found the item but price is missing in catalogue."
            return result
        try:
            qty = float(quantity)
        except (TypeError, ValueError):
            qty = 1.0
        if qty <= 0:
            qty = 1.0
        total = round(float(price) * qty, 2)
        result["requested_quantity"] = qty
        result["estimated_total_inr"] = total
        result["price_note"] = (
            "Indicative total only from catalogue rates. "
            "Shopkeeper confirms the final bill."
        )
        return result
