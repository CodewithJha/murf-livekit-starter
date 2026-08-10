"""Unit tests for Day 5 kirana catalogue lookup (no LiveKit / LLM required)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent import Assistant
from catalogue import DEFAULT_CSV_PATH, CatalogueStore

FIXTURE_CSV = """Category,name,mrp,discountPercent,availableQuantity,discountedSellingPrice,weightInGms,outOfStock,quantity
Fruits & Vegetables,Onion,2500,16,3,2100,1000,FALSE,1
Fruits & Vegetables,Tomato Hybrid,4200,16,3,3500,1000,FALSE,1
Dairy,Amul Milk 1L,6000,0,0,6000,1000,TRUE,1
Snacks,Britannia Biscuits,4000,10,12,3600,200,FALSE,1
"""


@pytest.fixture
def catalogue(tmp_path: Path) -> CatalogueStore:
    path = tmp_path / "zepto_catalogue.csv"
    path.write_text(FIXTURE_CSV, encoding="utf-8")
    return CatalogueStore(path)


def test_lookup_onion_in_stock(catalogue: CatalogueStore) -> None:
    result = catalogue.lookup("onion")
    assert result["found"] is True
    assert result["name"] == "Onion"
    assert result["stock_status"] == "low_stock"  # availableQuantity=3
    assert result["selling_price_inr"] == 21.0
    assert result["mrp_inr"] == 25.0
    assert "as_of" in result
    assert "scraped" in result["data_source"].lower() or "CSV" in result["data_source"]


def test_lookup_out_of_stock(catalogue: CatalogueStore) -> None:
    result = catalogue.lookup("Amul Milk")
    assert result["found"] is True
    assert result["stock_status"] == "out_of_stock"


def test_lookup_miss(catalogue: CatalogueStore) -> None:
    result = catalogue.lookup("dragonfruit juice")
    assert result["found"] is False
    assert result["error"] is False
    assert (
        "could not find" in result["message"].lower()
        or "No catalogue" in result["message"]
    )


def test_missing_file_fails_gracefully(tmp_path: Path) -> None:
    store = CatalogueStore(tmp_path / "does_not_exist.csv")
    result = store.lookup("onion")
    assert result["found"] is False
    assert result["error"] is True
    assert "unavailable" in result["message"].lower()


def test_estimate_line_total(catalogue: CatalogueStore) -> None:
    result = catalogue.estimate_line_total("biscuits", 2)
    assert result["found"] is True
    assert result["estimated_total_inr"] == 72.0
    assert result["requested_quantity"] == 2.0


@pytest.mark.asyncio
async def test_assistant_tool_uses_catalogue(catalogue: CatalogueStore) -> None:
    agent = Assistant(catalogue_store=catalogue)

    class _Ctx:
        @property
        def userdata(self) -> dict:
            return {}

    result = await agent.lookup_kirana_item(_Ctx(), item_name="tomato", quantity=1)
    assert result["found"] is True
    assert "Tomato" in result["name"]
    assert result["estimated_total_inr"] == 35.0


def test_default_csv_ships_with_repo() -> None:
    """Challenge demo needs the public Zepto-style CSV committed locally."""
    assert DEFAULT_CSV_PATH.is_file(), f"Missing catalogue at {DEFAULT_CSV_PATH}"
    store = CatalogueStore(DEFAULT_CSV_PATH)
    hit = store.lookup("onion")
    assert hit["found"] is True


def test_spoken_banana_and_hari_mirchi_on_real_csv() -> None:
    """Demo phrases must resolve to produce rows with a clear rupee price."""
    store = CatalogueStore(DEFAULT_CSV_PATH)

    bananas = store.lookup("3 bananas")
    assert bananas["found"] is True
    assert "Banana" in bananas["name"]
    assert "Leaf" not in bananas["name"]
    assert bananas["selling_price_inr"] is not None
    assert bananas["selling_price_inr"] > 0

    # Plural alone previously missed entirely.
    plural = store.lookup("bananas")
    assert plural["found"] is True
    assert plural["selling_price_inr"] is not None

    mirchi = store.lookup("aadha kilo hari mirchi")
    assert mirchi["found"] is True
    assert "Chilli Green" in mirchi["name"]
    assert mirchi["selling_price_inr"] == 16.0
    assert "Sauce" not in mirchi["name"]
