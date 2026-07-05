"""GraphQL types. Fields are declared alphabetically on purpose — GraphiQL's
Docs panel renders them in declaration order."""

import strawberry
import strawberry_django
from strawberry import auto
from strawberry.scalars import JSON

from apps.menu import models


@strawberry_django.type(models.HoursPeriod)
class HoursPeriod:
    """Operating hours for one handoff mode (pickup, drivethru, dispatch...).

    Times are strings as shipped by the feed; "24:00" appears and is preserved.
    """

    closes: auto
    day: auto
    end_day: auto
    handoff_type: auto
    opens: auto


@strawberry_django.type(models.Restaurant)
class Restaurant:
    """The store this menu belongs to. externalId is the restaurant ID from the
    source XML (24405 in this dataset)."""

    brand: auto
    city: auto
    country: auto
    external_id: auto
    hours: list[HoursPeriod]
    latitude: auto
    longitude: auto
    name: auto
    state: auto
    store_name: auto
    street_address: auto
    telephone: auto
    zip_code: auto


@strawberry_django.type(models.Ingredient)
class Ingredient:
    """Derived, not native to the feed: extracted from pipe-delimited product
    descriptions and "No X" removal options, normalized for typos and plurals.
    Heuristic by design - see DESIGN.md D6."""

    name: auto
    products: list["Product"]


@strawberry_django.type(models.Option)
class Option:
    """A selectable choice inside an option group (e.g. "Small", "No Bacon",
    "Extra Avocado"). isRemoval marks "No X" ingredient-removal options.
    childGroups nests further modifier levels - up to 5 deep in this menu."""

    adjusts_parent_calories: auto
    adjusts_parent_price: auto
    base_calories: auto
    child_groups: list["OptionGroup"]
    cost: auto
    external_id: auto
    is_default: auto
    is_removal: auto
    metadata: JSON
    name: auto
    price: auto
    sort_order: auto


@strawberry_django.type(models.OptionGroup)
class OptionGroup:
    """A modifier group: a set of options attached to a product (root level) or
    to a parent option (nested). Mandatory groups must be answered to order."""

    description: auto
    external_id: auto
    mandatory: auto
    metadata: JSON
    options: list[Option]
    # Set on root-level groups only; nested groups hang off a parent option.
    product: "Product | None"
    sort_order: auto


@strawberry_django.type(models.Product)
class Product:
    """A menu item. externalId is the stable product ID from the source XML.
    baseCalories/maxCalories are null when the feed provides no calorie data -
    such products are excluded from calorie-filtered results, not treated as 0."""

    base_calories: auto
    calories_separator: auto
    category: "Category"
    chain_external_id: auto
    cost: auto
    description: auto
    external_id: auto
    images: JSON
    ingredients: list[Ingredient]
    is_disabled: auto
    max_calories: auto
    metadata: JSON
    modifier_groups: list[OptionGroup]
    name: auto
    short_description: auto
    sort_order: auto


@strawberry_django.type(models.Category)
class Category:
    """Menu section. isSingleUse marks the non-food section of the feed
    (utensils and similar)."""

    external_id: auto
    is_single_use: auto
    name: auto
    products: list[Product]
    sort_order: auto


@strawberry.input(description="All criteria combine with AND. Omitted fields do not filter.")
class ProductFilter:
    available_only: bool = strawberry.field(
        default=True, description="When true (default), hide disabled products."
    )
    category_id: str | None = strawberry.field(
        default=None, description="Category externalId to restrict to."
    )
    exclude_ingredients: list[str] | None = strawberry.field(
        default=None, description="Product must contain NONE of these (allergen-style)."
    )
    include_ingredients: list[str] | None = strawberry.field(
        default=None,
        description='Product must contain ALL listed ingredients. Terms are normalized like ingest, so "eggs" matches "Egg".',
    )
    max_calories: int | None = strawberry.field(
        default=None,
        description="Inclusive upper bound on baseCalories. Products without calorie data are excluded.",
    )
    min_calories: int | None = strawberry.field(
        default=None,
        description="Inclusive lower bound on baseCalories. Products without calorie data are excluded.",
    )


@strawberry.type
class ProductPage:
    """One page of filtered products. totalCount is the full match count, not the page size."""

    items: list[Product]
    total_count: int


@strawberry_django.filter_type(models.Category, lookups=True)
class CategoryLookupFilter:
    """Per-field operator lookups on categories."""

    external_id: auto
    is_single_use: auto
    name: auto


@strawberry_django.filter_type(models.Product, lookups=True)
class ProductLookupFilter:
    """Generic per-field operators: text fields take exact/iContains/startsWith/...,
    numeric fields take gt/gte/lt/lte/range. Combinable with AND/OR/NOT."""

    base_calories: auto
    category: CategoryLookupFilter | None
    cost: auto
    description: auto
    external_id: auto
    is_disabled: auto
    max_calories: auto
    name: auto


@strawberry.type
class MenuSearchResult:
    """Menu-wide search hits, grouped by what matched: products (name or
    description), categories, modifier options, and derived ingredients."""

    categories: list[Category]
    ingredients: list[Ingredient]
    options: list[Option]
    products: list[Product]
