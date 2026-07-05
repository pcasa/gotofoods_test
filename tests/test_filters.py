from pathlib import Path

import pytest

from apps.menu.models import Product
from apps.menu.services.ingest import MenuIngestService
from apps.menu.services.queries import MenuQueryService

FIXTURE = Path(__file__).parent / "fixtures" / "menu_sample.xml"

# Fixture contents: Turkey Capri (1001, 500 cal, ingredients), Plain Soup
# (1002, no calories, no ingredients), Iced Tea (1003, 0 cal).


@pytest.fixture
def ingested(db):
    MenuIngestService().ingest(FIXTURE)


def _names(items: list[Product]) -> set[str]:
    return {product.name for product in items}


def test_max_calories_excludes_products_without_calorie_data(ingested):
    items, total = MenuQueryService.products(max_calories=600)
    assert _names(items) == {"Turkey Capri", "Iced Tea"}  # Plain Soup has no data
    assert total == 2


def test_min_calories(ingested):
    items, _ = MenuQueryService.products(min_calories=100)
    assert _names(items) == {"Turkey Capri"}


def test_include_ingredients_requires_all_terms(ingested):
    items, _ = MenuQueryService.products(include_ingredients=["bacon", "turkey"])
    assert _names(items) == {"Turkey Capri"}

    items, _ = MenuQueryService.products(include_ingredients=["bacon", "anchovies"])
    assert items == []


def test_include_ingredients_normalizes_like_ingest(ingested):
    # "eggs" (plural) must match the stored "Egg", derived from "No Eggs".
    items, _ = MenuQueryService.products(include_ingredients=["eggs"])
    assert _names(items) == {"Turkey Capri"}


def test_exclude_ingredients(ingested):
    items, _ = MenuQueryService.products(exclude_ingredients=["Bacon"])
    assert _names(items) == {"Plain Soup", "Iced Tea", "Cutlery Kit"}


def test_available_only_hides_disabled_products(ingested):
    Product.objects.filter(external_id="1003").update(is_disabled=True)
    items, _ = MenuQueryService.products()
    assert "Iced Tea" not in _names(items)
    items, _ = MenuQueryService.products(available_only=False)
    assert "Iced Tea" in _names(items)


def test_search_matches_name_and_description(ingested):
    items, _ = MenuQueryService.products(search="capri")
    assert _names(items) == {"Turkey Capri"}
    items, _ = MenuQueryService.products(search="comforting")
    assert _names(items) == {"Plain Soup"}


def test_category_filter(ingested):
    items, _ = MenuQueryService.products(category_external_id="101")
    assert _names(items) == {"Iced Tea"}


def test_pagination_slices_but_reports_full_total(ingested):
    items, total = MenuQueryService.products(first=1, offset=0)
    assert len(items) == 1
    assert total == 4
    page_two, _ = MenuQueryService.products(first=1, offset=1)
    assert page_two[0].external_id != items[0].external_id
