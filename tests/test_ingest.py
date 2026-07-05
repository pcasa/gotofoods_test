from pathlib import Path

import pytest
from django.db import IntegrityError

from apps.menu.models import (
    Category,
    HoursPeriod,
    Ingredient,
    Option,
    OptionGroup,
    Product,
    Restaurant,
)
from apps.menu.services.ingest import MenuIngestService

FIXTURE = Path(__file__).parent / "fixtures" / "menu_sample.xml"


def _snapshot() -> dict:
    return {
        "restaurants": Restaurant.objects.count(),
        "categories": Category.objects.count(),
        "products": Product.objects.count(),
        "groups": OptionGroup.objects.count(),
        "options": Option.objects.count(),
        "hours": HoursPeriod.objects.count(),
        "ingredients": Ingredient.objects.count(),
        "option_ids": set(Option.objects.values_list("external_id", flat=True)),
    }


@pytest.fixture
def ingested(db):
    MenuIngestService().ingest(FIXTURE)


def test_ingest_loads_expected_counts(ingested):
    snap = _snapshot()
    assert snap["restaurants"] == 1
    assert snap["categories"] == 3
    assert snap["products"] == 4
    assert snap["groups"] == 4
    assert snap["options"] == 7
    assert snap["hours"] == 2

    utensils = Category.objects.get(external_id="102")
    assert utensils.is_single_use is True
    assert Category.objects.get(external_id="100").is_single_use is False


def test_ingest_is_idempotent(ingested):
    first = _snapshot()
    MenuIngestService().ingest(FIXTURE)
    assert _snapshot() == first


def test_product_fields_and_ingredients(ingested):
    turkey = Product.objects.get(external_id="1001")
    assert turkey.base_calories == 500
    assert turkey.max_calories == 1580
    assert turkey.images[0]["url"] == "https://example.test/turkey.jpg"

    by_name = {
        link.ingredient.name: link.source for link in turkey.product_ingredients.all()
    }
    assert by_name == {
        "Turkey": "both",
        "Bacon": "description",
        "Mozzarella": "description",
        "Banana Pepper": "description",
        "Egg": "removal_option",
        "Chopped Roasted Vegetables": "removal_option",
    }

    soup = Product.objects.get(external_id="1002")
    assert soup.base_calories is None
    assert soup.product_ingredients.count() == 0

    tea = Product.objects.get(external_id="1003")
    assert tea.base_calories == 0


def test_modifier_tree_nesting_and_removal_flag(ingested):
    deep_group = OptionGroup.objects.get(external_id="9004")
    assert deep_group.product is None
    assert deep_group.parent_option.external_id == "8005"

    root_group = OptionGroup.objects.get(external_id="9001")
    assert root_group.product.external_id == "1001"
    assert root_group.parent_option is None

    assert Option.objects.get(external_id="8002").is_removal is True
    assert Option.objects.get(external_id="8001").is_removal is False


def test_option_group_requires_exactly_one_parent(db):
    with pytest.raises(IntegrityError):
        OptionGroup.objects.create(external_id="bad-1", description="orphan")
